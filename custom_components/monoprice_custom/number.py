"""Support for Monoprice 6-Zone Amplifier EQ controls via number entities."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .__init__ import MonopriceConfigEntry

_LOGGER = logging.getLogger(__name__)

PARALLEL_UPDATES = 1


async def async_setup_entry(
    hass: HomeAssistant,
    entry: MonopriceConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Monoprice number entities from a config entry."""
    coordinator = entry.runtime_data.coordinator

    entities = []
    # Loop ONLY over detected units
    for unit in coordinator.active_units:
        for j in range(1, 7):
            zone_id = (unit * 10) + j
            for control_type in ("Balance", "Bass", "Treble"):
                entities.append(
                    MonopriceZoneNumber(
                        coordinator,
                        entry.entry_id,
                        zone_id,
                        control_type,
                    )
                )

    async_add_entities(entities)


class MonopriceZoneNumber(CoordinatorEntity, NumberEntity):
    """Representation of a Monoprice zone number control."""

    _attr_has_entity_name = True
    _attr_mode = NumberMode.SLIDER
    _attr_native_step = 1.0

    def __init__(
        self,
        coordinator,
        entry_id: str,
        zone_id: int,
        control_type: str,
    ) -> None:
        """Initialize new zone number controls."""
        super().__init__(coordinator)
        self._zone_id = zone_id
        self._control_type = control_type

        self._attr_unique_id = f"{entry_id}_{self._zone_id}_{self._control_type}"
        self._attr_name = f"{control_type} level"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{entry_id}_{self._zone_id}")},
            manufacturer="Monoprice",
            model="6-Zone Amplifier",
            name=f"Zone {self._zone_id}",
        )

        if control_type == "Balance":
            self._attr_native_min_value = 0
            self._attr_native_max_value = 20
            self._attr_icon = "mdi:scale-balance"
        elif control_type == "Bass":
            self._attr_native_min_value = -7
            self._attr_native_max_value = 14
            self._attr_icon = "mdi:speaker"
        elif control_type == "Treble":
            self._attr_native_min_value = -7
            self._attr_native_max_value = 14
            self._attr_icon = "mdi:surround-sound"

    @property
    def entity_registry_enabled_default(self) -> bool:
        """Return if the entity should be enabled when first added to the entity registry."""
        if self._zone_id in (10, 20, 30):
            return False
        return self._zone_id < 20 or (
            self.coordinator.data is not None and self._zone_id in self.coordinator.data
        )

    @property
    def zone_data(self) -> Any | None:
        """Helper to retrieve current zone state from coordinator."""
        if not self.coordinator.data:
            return None
        return self.coordinator.data.get(self._zone_id)

    @property
    def native_value(self) -> float | None:
        """Return the current value."""
        if not self.zone_data:
            return None

        if self._control_type == "Balance":
            return self.zone_data.balance
        if self._control_type == "Bass":
            return self.zone_data.bass
        if self._control_type == "Treble":
            return self.zone_data.treble
        return None

    async def async_set_native_value(self, value: float) -> None:
        """Update the current value asynchronously."""
        target_val = int(value)
        if self._control_type == "Balance":
            await self.hass.async_add_executor_job(
                self.coordinator.api.set_balance, self._zone_id, target_val
            )
        elif self._control_type == "Bass":
            await self.hass.async_add_executor_job(
                self.coordinator.api.set_bass, self._zone_id, target_val
            )
        elif self._control_type == "Treble":
            await self.hass.async_add_executor_job(
                self.coordinator.api.set_treble, self._zone_id, target_val
            )

        await self.coordinator.async_request_refresh()
