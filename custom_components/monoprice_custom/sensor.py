"""Support for Monoprice 6-Zone Amplifier sensors."""
from __future__ import annotations

import logging
from typing import Any

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
            for sensor_type in ("Keypad", "Public Announcement", "Do Not Disturb"):
                entities.append(
                    MonopriceZoneSensor(
                        coordinator,
                        entry.entry_id,
                        zone_id,
                        sensor_type,
                    )
                )

    async_add_entities(entities)


class MonopriceZoneSensor(CoordinatorEntity, SensorEntity):
    """Representation of a Monoprice zone status sensor."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator,
        entry_id: str,
        zone_id: int,
        sensor_type: str,
    ) -> None:
        """Initialize new zone sensor."""
        super().__init__(coordinator)
        self._zone_id = zone_id
        self._sensor_type = sensor_type

        # Create clean unique ID slug
        clean_type = sensor_type.lower().replace(" ", "_")
        self._attr_unique_id = f"{entry_id}_{self._zone_id}_{clean_type}"
        self._attr_name = sensor_type

        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{entry_id}_{self._zone_id}")},
            manufacturer="Monoprice",
            model="6-Zone Amplifier",
            name=f"Zone {self._zone_id}",
        )

        if sensor_type == "Keypad":
            self._attr_icon = "mdi:dialpad"
        elif "Public" in sensor_type:
            self._attr_icon = "mdi:bullhorn"
        elif sensor_type == "Do Not Disturb":
            self._attr_icon = "mdi:weather-night"

    @property
    def entity_registry_enabled_default(self) -> bool:
        """Return if entity is enabled by default when first added."""
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
    def native_value(self) -> str | None:
        """Return the current state value."""
        if not self.zone_data:
            return None

        if self._sensor_type == "Keypad":
            return "Connected" if getattr(self.zone_data, "keypad", False) else "Disconnected"
        if "Public" in self._sensor_type:
            return "On" if getattr(self.zone_data, "pa", False) else "Off"
        if self._sensor_type == "Do Not Disturb":
            return "On" if getattr(self.zone_data, "do_not_disturb", False) else "Off"

        return None
