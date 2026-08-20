"""Support for Monoprice 6-Zone Amplifier sensors."""
from __future__ import annotations

import logging

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import MonopriceConfigEntry
from .coordinator import MonopriceCoordinator
from .device import zone_device_info

_LOGGER = logging.getLogger(__name__)

PARALLEL_UPDATES = 1

KEYPAD_OPTIONS = ["connected", "disconnected"]


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
    """Representation of a Monoprice zone keypad connection status."""

    _attr_has_entity_name = True
    _attr_translation_key = "keypad_status"
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = KEYPAD_OPTIONS
    _attr_icon = "mdi:dialpad"

    def __init__(self, coordinator: MonopriceCoordinator, entry_id: str, zone_id: int) -> None:
        """Initialize keypad sensor."""
        super().__init__(coordinator)
        self._zone_id = zone_id
        self._attr_unique_id = f"{entry_id}_{zone_id}_keypad_status"
        self._attr_device_info = zone_device_info(entry_id, zone_id)

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

        return "connected" if getattr(zone_status, "keypad", False) else "disconnected"
