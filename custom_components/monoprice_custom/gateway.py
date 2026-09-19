"""Single-owner asynchronous gateway for all Monoprice serial traffic."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from enum import StrEnum
from time import monotonic
from typing import Any, Final, TypeVar

import serialx
from homeassistant.core import HomeAssistant
from pymonoprice import ZoneStatus

from .api import MonopriceExtended
from .serial import POWER_ON_BAUD_RATE, SUPPORTED_BAUD_RATES

_LOGGER = logging.getLogger(__name__)
_T = TypeVar("_T")
# Floor between consecutive RS-232 commands. pyxantech sets this on every
# series it supports and enforces it with an explicit sleep, to stop the
# amplifier timing out when commands arrive faster than it answers; its
# README records the value moving from 400ms to 50ms.
MIN_COMMAND_INTERVAL: Final = 0.05
_COMMUNICATION_ERRORS = (
    serialx.SerialException,
    TimeoutError,
    PermissionError,
    OSError,
)


class ConnectionState(StrEnum):
    """Lifecycle states exposed through diagnostics."""

    CONNECTING = "connecting"
    CONNECTED = "connected"
    RECOVERING = "recovering"
    DISCONNECTED = "disconnected"
    CLOSING = "closing"
    CLOSED = "closed"


class GatewayClosedError(RuntimeError):
    """Raised when serial work is submitted after shutdown begins."""


class MonopriceGateway:
    """Own one client and serialize every byte through one async queue lock."""

    def __init__(
        self,
        hass: HomeAssistant,
        api: MonopriceExtended,
        last_known_baud: int = POWER_ON_BAUD_RATE,
    ) -> None:
        """Initialize the client owner."""
        self.hass = hass
        self.api = api
        self._io_lock = asyncio.Lock()
        self._closing = False
        self.connection_state = ConnectionState.CONNECTING
        self.last_known_baud = (
            last_known_baud
            if last_known_baud in SUPPORTED_BAUD_RATES
            else POWER_ON_BAUD_RATE
        )
        self.failure_count = 0
        self.reconnect_count = 0
        # The rate the amplifier was found on, before any negotiation moved
        # it to the target. A power cycle resets the amplifier to 9600, so
        # this is what tells a power event apart from a link fault.
        self.last_detected_baud: int | None = None
        # Learned from the hardware: the highest rate confirmed on this
        # cabling, and the lowest that failed to confirm. Seeded from the
        # config entry and written back by the coordinator.
        self.proven_baud: int | None = None
        self.failed_baud: int | None = None
        self._last_command_at = 0.0

    @property
    def current_baud_rate(self) -> int:
        """Return the local port speed without performing serial I/O."""
        return self.api.current_baud_rate

    async def _async_locked_call(self, function: Callable[..., _T], *args: Any) -> _T:
        """Run one synchronous client operation under the gateway lock."""
        if self._closing:
            raise GatewayClosedError("Monoprice gateway is closing")

        async with self._io_lock:
            if self._closing:
                raise GatewayClosedError("Monoprice gateway is closing")
            await self._async_hold_command_floor()
            try:
                result = await self.hass.async_add_executor_job(function, *args)
            except _COMMUNICATION_ERRORS:
                self.failure_count += 1
                self.connection_state = ConnectionState.DISCONNECTED
                raise
            finally:
                # Space from when this command finished, not when it started,
                # so a slow command does not get a second delay stacked on it.
                self._last_command_at = monotonic()
            self.connection_state = ConnectionState.CONNECTED
            return result

    async def _async_hold_command_floor(self) -> None:
        """Wait out any remainder of the minimum inter-command interval.

        Serializing through the lock keeps commands from overlapping but lets
        them run back to back, which is what the floor is for. Held inside the
        lock so the wait is never skipped by a caller that took it first.
        """
        remaining = MIN_COMMAND_INTERVAL - (monotonic() - self._last_command_at)
        if remaining > 0:
            await asyncio.sleep(remaining)

    async def async_execute(self, method: str, *args: Any) -> Any:
        """Run an API method through the single serialized gateway."""
        return await self._async_locked_call(getattr(self.api, method), *args)

    async def async_zone_status(self, zone: int) -> ZoneStatus | None:
        """Read one zone through the gateway."""
        return await self._async_locked_call(self.api.zone_status, zone)

    async def async_wake(self) -> None:
        """Send the wake sequence through the same serialized path."""
        await self._async_locked_call(self.api.wake)

    def _locate_sync(self, *preferred: int) -> int | None:
        """Return the rate the amplifier answers on, trying `preferred` first."""
        ordered = tuple(dict.fromkeys(preferred + SUPPORTED_BAUD_RATES))
        tried: list[int] = []
        for candidate in ordered:
            if candidate not in SUPPORTED_BAUD_RATES:
                continue
            tried.append(candidate)
            if self.api.probe_baud_rate(candidate):
                _LOGGER.debug(
                    "Amplifier answered at %d baud (tried %s)", candidate, tried
                )
                return candidate
        _LOGGER.debug("No answer at any supported rate (tried %s)", tried)
        return None

    def _ceiling(self, target_baud: int) -> int:
        """Return the highest rate worth attempting on this cabling.

        A rate that once failed to confirm is not tried again: the amplifier
        switches on receipt, so a rate the wiring cannot carry leaves it
        unreachable until it loses power. Having learned that once is enough.
        """
        ceiling = target_baud
        if self.failed_baud is not None:
            usable = [b for b in SUPPORTED_BAUD_RATES if b < self.failed_baud]
            ceiling = min(ceiling, usable[-1] if usable else POWER_ON_BAUD_RATE)
        return ceiling

    def _next_rate(self, detected_baud: int, target_baud: int, auto: bool) -> int:
        """Return the rate to move to from `detected_baud`.

        Manual mode goes straight to the configured rate, which is what a user
        who has chosen one expects. Automatic mode treats it as a ceiling and
        climbs one supported step per link-up, except that a rate already
        proven on this cabling can be returned to directly, since it is known
        to work.
        """
        if not auto:
            return target_baud

        ceiling = self._ceiling(target_baud)
        if detected_baud >= ceiling:
            return ceiling
        if self.proven_baud is not None and detected_baud < self.proven_baud:
            return min(self.proven_baud, ceiling)

        higher = [b for b in SUPPORTED_BAUD_RATES if b > detected_baud]
        return min(higher[0], ceiling) if higher else ceiling

    def _ensure_link_sync(
        self, target_baud: int, auto: bool = True
    ) -> tuple[int, bool]:
        """Find the amplifier, then move one step toward the wanted rate."""
        initial_baud = self.api.current_baud_rate
        detected_baud = self._locate_sync(
            POWER_ON_BAUD_RATE, self.last_known_baud, target_baud, initial_baud
        )
        if detected_baud is None:
            raise serialx.SerialTimeoutException(
                "No Monoprice response at any bounded recovery baud rate"
            )

        # Record where it answered before negotiating away from it.
        self.last_detected_baud = detected_baud

        wanted = self._next_rate(detected_baud, target_baud, auto)
        _LOGGER.debug(
            "Link speed: found at %d, want %d (ceiling %d, %s, proven %s, failed %s)",
            detected_baud,
            wanted,
            self._ceiling(target_baud),
            "automatic" if auto else "manual",
            self.proven_baud,
            self.failed_baud,
        )
        if wanted != detected_baud:
            if self.api.set_baud_rate(wanted):
                self.proven_baud = max(wanted, self.proven_baud or 0)
                detected_baud = wanted
            else:
                # The amplifier switched on receipt whether or not it answered,
                # so it is now at `wanted` and this end is not. Look for it
                # before giving up: an unlucky confirmation is recoverable, a
                # rate the wiring cannot carry is not.
                self.failed_baud = wanted
                _LOGGER.warning(
                    "Monoprice did not confirm %d baud; it will not be tried "
                    "again on this connection",
                    wanted,
                )
                relocated = self._locate_sync(wanted)
                if relocated is None:
                    raise serialx.SerialTimeoutException(
                        f"Monoprice did not confirm {wanted} baud and cannot be "
                        "found at any supported rate. Remove power from the "
                        "amplifier for 30 seconds to return it to "
                        f"{POWER_ON_BAUD_RATE} baud."
                    )
                detected_baud = relocated

        return detected_baud, initial_baud != detected_baud

    async def async_ensure_link(self, target_baud: int, auto: bool = True) -> int:
        """Recover at 9600 first, then move toward the wanted rate.

        `auto` treats `target_baud` as a ceiling to climb toward rather than a
        rate to insist on; see `_next_rate`.
        """
        if target_baud not in SUPPORTED_BAUD_RATES:
            raise ValueError(f"Unsupported baud rate: {target_baud}")
        self.connection_state = ConnectionState.RECOVERING
        baud, changed = await self._async_locked_call(
            self._ensure_link_sync, target_baud, auto
        )
        self.last_known_baud = baud
        if changed:
            self.reconnect_count += 1
        self.connection_state = ConnectionState.CONNECTED
        return baud

    async def async_close(self) -> None:
        """Reject new work, drain in-flight I/O, and close the serial port."""
        if self.connection_state is ConnectionState.CLOSED:
            return
        self._closing = True
        self.connection_state = ConnectionState.CLOSING
        async with self._io_lock:
            await self.hass.async_add_executor_job(self.api.close)
        self.connection_state = ConnectionState.CLOSED
