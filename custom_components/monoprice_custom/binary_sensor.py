"""Connectivity diagnostics for the amplifier as a whole."""

from __future__ import annotations

from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .__init__ import MonopriceConfigEntry
from .device import controller_device_info


async def async_setup_entry(
    hass: HomeAssistant,
    entry: MonopriceConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the single amplifier-wide connectivity sensor."""
    coordinator = entry.runtime_data.coordinator
    async_add_entities([MonopriceConnectionSensor(coordinator, entry.entry_id)])


class MonopriceConnectionSensor(CoordinatorEntity, BinarySensorEntity):
    """Whether the amplifier is currently reachable.

    This entity deliberately never reports itself unavailable. A
    `CoordinatorEntity` normally goes unavailable when the coordinator's update
    fails, which for a connectivity sensor means it would stop reporting at
    exactly the moment it has something to say: "unavailable" instead of
    "disconnected", with nothing for an automation to trigger on. Overriding
    `available` keeps it readable through an outage, which is its whole job.
    """

    _attr_has_entity_name = True
    _attr_name = "Connection"
    _attr_translation_key = "connection"
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator, entry_id: str) -> None:
        """Initialize the connectivity sensor."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry_id}_connection"
        self._attr_device_info = controller_device_info(entry_id)

    @property
    def available(self) -> bool:
        """Always available; see the class docstring."""
        return True

    @property
    def is_on(self) -> bool:
        """Return True while the amplifier is answering."""
        return self.coordinator.is_online

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the outage history a serial problem is diagnosed from."""
        coordinator = self.coordinator
        gateway = coordinator.gateway
        duration = coordinator.last_outage_duration
        return {
            "current_baud": gateway.current_baud_rate,
            "target_baud": coordinator.target_baud_rate,
            "detected_baud": gateway.last_detected_baud,
            "offline_since": (
                coordinator.offline_since.isoformat()
                if coordinator.offline_since
                else None
            ),
            "last_offline_at": (
                coordinator.last_offline_at.isoformat()
                if coordinator.last_offline_at
                else None
            ),
            "last_outage_seconds": (
                round(duration.total_seconds()) if duration else None
            ),
            "last_outage_cause": coordinator.last_outage_cause,
            "outage_count": coordinator.outage_count,
            "consecutive_failures": coordinator.consecutive_failures,
            "retry_in_seconds": coordinator.retry_delay,
            "active_units": coordinator.active_units,
            "reconnect_count": gateway.reconnect_count,
        }
