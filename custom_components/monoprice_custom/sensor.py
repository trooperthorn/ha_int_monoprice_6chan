"""Support for Monoprice 6-Zone Amplifier sensors."""
from __future__ import annotations

import logging

from homeassistant.components.sensor import SensorEntity
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
    """Set up Monoprice sensor entities from a config entry."""
    coordinator = entry.runtime_data.coordinator

    entities = []
    # Loop ONLY over dynamically detected active units
    for unit in coordinator.active_units:
        for j in range(1, 7):
            zone_id = (unit * 10) + j
            entities.append(MonopriceKeypadSensor(coordinator, entry.entry_id, zone_id))

    async_add_entities(entities)


class MonopriceKeypadSensor(CoordinatorEntity, SensorEntity):
    """Representation of a Monoprice zone keypad status sensor."""

    _attr_has_entity_name = True
    _attr_name = "Keypad Status"
    _attr_icon = "mdi:dialpad"

    def __init__(self, coordinator, entry_id: str, zone_id: int) -> None:
        """Initialize keypad sensor."""
        super().__init__(coordinator)
        self._zone_id = zone_id
        self._attr_unique_id = f"{entry_id}_{zone_id}_keypad_status"

        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{entry_id}_{zone_id}")},
            manufacturer="Monoprice",
            model="6-Zone Amplifier",
            name=f"Zone {zone_id}",
        )

    @property
    def entity_registry_enabled_default(self) -> bool:
        """Enable by default."""
        return True

    @property
    def native_value(self) -> str | None:
        """Return keypad connection status."""
        if not self.coordinator.data or self._zone_id not in self.coordinator.data:
            return None
        
        zone_status = self.coordinator.data.get(self._zone_id)
        if not zone_status:
            return None
            
        return "Connected" if getattr(zone_status, "keypad", False) else "Disconnected"
