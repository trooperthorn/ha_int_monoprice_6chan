"""Coordinator for the Monoprice 6-Zone Amplifier integration."""
from __future__ import annotations

from datetime import timedelta
import logging

from serial import SerialException, SerialTimeoutException

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import POWER_ON_BAUD_RATE, SUPPORTED_BAUD_RATES, MonopriceExtended
from .const import CONF_BAUD_RATE

_LOGGER = logging.getLogger(__name__)

DEFAULT_TARGET_BAUD = 38400
UPDATE_INTERVAL = timedelta(seconds=5)


class MonopriceCoordinator(DataUpdateCoordinator):
    """Class to manage fetching Monoprice data asynchronously."""

    def __init__(
        self,
        hass: HomeAssistant,
        api: MonopriceExtended,
        entry: ConfigEntry,
    ) -> None:
        """Initialize."""
        self.api = api
        self.entry = entry

        self.active_units: list[int] = []
        self._baud_optimized = False

        super().__init__(
            hass,
            _LOGGER,
            name="Monoprice 6-Zone",
            update_interval=UPDATE_INTERVAL,
        )

    @property
    def target_baud_rate(self) -> int:
        """Baud rate to negotiate up to, configurable via the options flow."""
        configured = self.entry.options.get(CONF_BAUD_RATE, DEFAULT_TARGET_BAUD)
        return configured if configured in SUPPORTED_BAUD_RATES else DEFAULT_TARGET_BAUD

    async def _async_discover_active_units(self) -> None:
        """One-time discovery of which expansion units are physically present."""
        active = [1]
        try:
            if _LOGGER.isEnabledFor(logging.DEBUG):
                _LOGGER.debug("Probing for expansion Unit 2 (Zone 21)...")
            status_u2 = await self.hass.async_add_executor_job(self.api.zone_status, 21)
            if status_u2:
                active.append(2)

                if _LOGGER.isEnabledFor(logging.DEBUG):
                    _LOGGER.debug("Probing for expansion Unit 3 (Zone 31)...")
                status_u3 = await self.hass.async_add_executor_job(self.api.zone_status, 31)
                if status_u3:
                    active.append(3)
        except Exception:
            pass
        self.active_units = active

        if _LOGGER.isEnabledFor(logging.DEBUG):
            _LOGGER.debug("Active units locked to: %s", self.active_units)

    async def async_refresh_zone(self, zone_id: int) -> None:
        """Refresh a single zone's status and publish it immediately.

        Used after issuing a set-command so the entity that triggered it
        reflects the new state without waiting on the next full poll cycle
        (or on every other zone being re-polled first).
        """
        try:
            status = await self.hass.async_add_executor_job(self.api.zone_status, zone_id)
        except (SerialException, SerialTimeoutException):
            await self.async_request_refresh()
            return

        if status is None:
            return

        new_data = dict(self.data or {})
        new_data[zone_id] = status
        self.async_set_updated_data(new_data)

    async def _async_update_data(self):
        """Fetch data from the amp via executor job."""
        try:
            if not self._baud_optimized:
                await self.hass.async_add_executor_job(self._async_optimize_baud_rate_sync)
                self._baud_optimized = True

            if not self.active_units:
                await self._async_discover_active_units()

            # Wake-up ping
            try:
                if _LOGGER.isEnabledFor(logging.DEBUG):
                    _LOGGER.debug("Sending wake-up ping to amplifier.")
                await self.hass.async_add_executor_job(self.api._port.write, b"\r\n")
            except Exception as e:
                if _LOGGER.isEnabledFor(logging.DEBUG):
                    _LOGGER.debug("Wake-up ping failed (expected if locked): %s", e)

            zones = {}

            for unit in self.active_units:
                for j in range(1, 7):
                    zone_id = (unit * 10) + j

                    if _LOGGER.isEnabledFor(logging.DEBUG):
                        _LOGGER.debug("Requesting status for Zone %s", zone_id)

                    try:
                        zone_status = await self.hass.async_add_executor_job(
                            self.api.zone_status, zone_id
                        )

                        if zone_status:
                            if _LOGGER.isEnabledFor(logging.DEBUG):
                                _LOGGER.debug(
                                    "Zone %s Response: Power=%s, Volume=%s, Source=%s",
                                    zone_id, zone_status.power, zone_status.volume, zone_status.source
                                )
                            zones[zone_id] = zone_status

                    except Exception as loop_err:
                        if "Connection timed out" in str(loop_err):
                            if _LOGGER.isEnabledFor(logging.DEBUG):
                                _LOGGER.debug("Timeout requesting Zone %s (Unit %s may not exist)", zone_id, unit)
                            if unit > 1:
                                pass  # Ignore timeouts for secondary units
                            else:
                                raise loop_err
                        else:
                            raise loop_err

                # Poll Master Zone for unit (10, 20, 30)
                try:
                    master_id = unit * 10
                    master_status = await self.hass.async_add_executor_job(
                        self.api.zone_status, master_id
                    )
                    if master_status:
                        zones[master_id] = master_status
                except Exception:
                    pass

            return zones

        except (SerialException, SerialTimeoutException) as err:
            self._baud_optimized = False
            _LOGGER.warning(
                "Monoprice communication error (%s). Connection state reset; re-negotiating baud rate on next poll.",
                err,
            )
            raise UpdateFailed(f"Error communicating with API: {err}")
        except Exception as err:
            raise UpdateFailed(f"Error communicating with API: {err}")

    def _async_optimize_baud_rate_sync(self) -> None:
        """Synchronous wrapper so the whole negotiation runs in one executor job."""
        target = self.target_baud_rate
        current = self.api._port.baudrate

        if current == target:
            return

        try:
            self.api.zone_status(11)
        except Exception:
            self.api._port.baudrate = POWER_ON_BAUD_RATE
            self.api._port.reset_input_buffer()
            self.api._port.reset_output_buffer()
            current = POWER_ON_BAUD_RATE

        if current == target:
            return

        if target != POWER_ON_BAUD_RATE:
            _LOGGER.info(
                "Negotiating Monoprice amplifier link speed up to %d baud", target
            )
            self.api.set_baud_rate(target)
