"""Single-owner asynchronous gateway for all Monoprice serial traffic."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from enum import StrEnum
from time import monotonic
from typing import Any, Final, TypeVar

import serialx
from homeassistant.core import HomeAssistant
from pymonoprice import ZoneStatus

from .api import MonopriceExtended
from .serial import POWER_ON_BAUD_RATE, SUPPORTED_BAUD_RATES

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

    def _ensure_link_sync(self, target_baud: int) -> tuple[int, bool]:
        """Synchronously find the amplifier rate and negotiate the target."""
        initial_baud = self.api.current_baud_rate
        candidates = tuple(
            dict.fromkeys(
                (
                    POWER_ON_BAUD_RATE,
                    self.last_known_baud,
                    target_baud,
                    initial_baud,
                )
            )
        )
        detected_baud: int | None = None
        for candidate in candidates:
            if candidate in SUPPORTED_BAUD_RATES and self.api.probe_baud_rate(
                candidate
            ):
                detected_baud = candidate
                break

        if detected_baud is None:
            raise serialx.SerialTimeoutException(
                "No Monoprice response at any bounded recovery baud rate"
            )

        if detected_baud != target_baud:
            if not self.api.set_baud_rate(target_baud):
                raise serialx.SerialTimeoutException(
                    f"Monoprice did not confirm target baud rate {target_baud}"
                )
            detected_baud = target_baud

        return detected_baud, initial_baud != detected_baud

    async def async_ensure_link(self, target_baud: int) -> int:
        """Recover at 9600 first, then negotiate a supported target rate."""
        if target_baud not in SUPPORTED_BAUD_RATES:
            raise ValueError(f"Unsupported baud rate: {target_baud}")
        self.connection_state = ConnectionState.RECOVERING
        baud, changed = await self._async_locked_call(
            self._ensure_link_sync, target_baud
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
