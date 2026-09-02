"""Coordinator for the Monoprice 6-Zone Amplifier integration."""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from time import monotonic

import serialx
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from pymonoprice import ZoneStatus

from .const import CONF_BAUD_RATE, CONF_LAST_KNOWN_BAUD
from .gateway import MonopriceGateway
from .serial import POWER_ON_BAUD_RATE, SUPPORTED_BAUD_RATES

_LOGGER = logging.getLogger(__name__)

DEFAULT_TARGET_BAUD = POWER_ON_BAUD_RATE
UPDATE_INTERVAL = timedelta(seconds=5)
EXPANSION_DISCOVERY_INTERVAL = timedelta(minutes=5)
_COMMUNICATION_ERRORS = (serialx.SerialException, TimeoutError, OSError)


class MonopriceCoordinator(DataUpdateCoordinator[dict[int, ZoneStatus]]):
    """Manage polling, recovery, and expansion-unit discovery."""

    def __init__(
        self,
        hass: HomeAssistant,
        gateway: MonopriceGateway,
        entry: ConfigEntry,
    ) -> None:
        """Initialize the coordinator."""
        self.gateway = gateway
        self.entry = entry
        self.active_units: list[int] = []
        self.last_successful_poll: datetime | None = None
        self.last_poll_duration: float | None = None
        self._link_ready = False
        self._next_expansion_discovery = 0.0

        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name="Monoprice 6-Zone",
            update_interval=UPDATE_INTERVAL,
        )

    @property
    def target_baud_rate(self) -> int:
        """Return the configured target link speed."""
        configured = self.entry.options.get(CONF_BAUD_RATE, DEFAULT_TARGET_BAUD)
        return (
            int(configured)
            if int(configured) in SUPPORTED_BAUD_RATES
            else DEFAULT_TARGET_BAUD
        )

    async def _async_ensure_link(self) -> None:
        """Run bounded recovery and target-baud negotiation when required."""
        if self._link_ready:
            return
        previous_baud = self.gateway.last_known_baud
        detected_baud = await self.gateway.async_ensure_link(self.target_baud_rate)
        self._link_ready = True
        self._next_expansion_discovery = 0.0

        if (
            detected_baud != previous_baud
            or self.entry.data.get(CONF_LAST_KNOWN_BAUD) != detected_baud
        ):
            self.hass.config_entries.async_update_entry(
                self.entry,
                data={**self.entry.data, CONF_LAST_KNOWN_BAUD: detected_baud},
            )

    async def _async_discover_active_units(self) -> None:
        """Rediscover expansion units at startup, after recovery, and periodically."""
        active = [1]
        for unit in (2, 3):
            if unit == 3 and 2 not in active:
                break
            try:
                status = await self.gateway.async_zone_status(unit * 10 + 1)
            except _COMMUNICATION_ERRORS:
                break
            if status is None:
                break
            active.append(unit)

        if active != self.active_units:
            _LOGGER.info("Detected Monoprice amplifier units: %s", active)
            self.active_units = active
        self._next_expansion_discovery = (
            monotonic() + EXPANSION_DISCOVERY_INTERVAL.total_seconds()
        )

    async def async_refresh_zone(self, zone_id: int) -> None:
        """Refresh one zone and publish it immediately."""
        try:
            status = await self.gateway.async_zone_status(zone_id)
        except _COMMUNICATION_ERRORS:
            self._link_ready = False
            await self.async_request_refresh()
            return

        if status is None:
            return
        new_data = dict(self.data or {})
        new_data[zone_id] = status
        self.async_set_updated_data(new_data)

    async def _async_update_data(self) -> dict[int, ZoneStatus]:
        """Fetch all known zones through the single gateway."""
        started = monotonic()
        try:
            await self._async_ensure_link()
            if monotonic() >= self._next_expansion_discovery:
                await self._async_discover_active_units()

            await self.gateway.async_wake()
            zones: dict[int, ZoneStatus] = {}
            for unit in self.active_units:
                for zone_id in range(unit * 10 + 1, unit * 10 + 7):
                    try:
                        status = await self.gateway.async_zone_status(zone_id)
                    except _COMMUNICATION_ERRORS:
                        if unit == 1:
                            raise
                        _LOGGER.debug(
                            "Expansion unit %d stopped responding during polling", unit
                        )
                        self._next_expansion_discovery = 0.0
                        break
                    if status is not None:
                        zones[zone_id] = status

                try:
                    master_status = await self.gateway.async_zone_status(unit * 10)
                except _COMMUNICATION_ERRORS:
                    if unit == 1:
                        raise
                else:
                    if master_status is not None:
                        zones[unit * 10] = master_status

            self.last_successful_poll = datetime.now(UTC)
            return zones
        except _COMMUNICATION_ERRORS as err:
            self._link_ready = False
            self._next_expansion_discovery = 0.0
            _LOGGER.warning(
                "Monoprice communication failed; bounded recovery will run on the "
                "next poll: %s",
                err,
            )
            raise UpdateFailed(f"Error communicating with amplifier: {err}") from err
        except Exception as err:
            raise UpdateFailed(f"Error communicating with amplifier: {err}") from err
        finally:
            self.last_poll_duration = monotonic() - started
