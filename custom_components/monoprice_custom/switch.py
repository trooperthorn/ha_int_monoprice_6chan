"""Support for Monoprice 6-Zone Amplifier switches."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .__init__ import MonopriceConfigEntry

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: MonopriceConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Monoprice switch entities."""
    coordinator = entry.runtime_data.coordinator

    entities = []
    # Loop over units 1-3, zones 1-6
    for i in range(1, 4):
        for j in range(1, 7):
            zone_id = (i * 10) + j
            entities.append(MonopricePASwitch(coordinator, entry.entry_id, zone_id))
            entities.append(MonopriceDNDSwitch(coordinator, entry.entry_id, zone_id))

    async_add_entities(entities)


class MonopricePASwitch(CoordinatorEntity, SwitchEntity):
    """Representation of a Monoprice Public Address (PA) switch."""

    _attr_has_entity_name = True
    _attr_name = "Public Address"

    def __init__(self, coordinator, entry_id: str, zone_id: int) -> None:
        """Initialize PA switch."""
        super().__init__(coordinator)
        self._zone_id = zone_id
        self._attr_unique_id = f"{entry_id}_{zone_id}_pa"

    @property
    def entity_registry_enabled_default(self) -> bool:
        """Only enable if zone exists or is unit 1."""
        if self._zone_id in (10, 20, 30):
            return False
        return self._zone_id < 20 or (self.coordinator.data and self._zone_id in self.coordinator.data)

    @property
    def is_on(self) -> bool | None:
        """Return true if PA is active."""
        if not self.coordinator.data or self._zone_id not in self.coordinator.data:
            return None
        return getattr(self.coordinator.data[self._zone_id], "pa", False)

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn PA on."""
        await self.hass.async_add_executor_job(
            self.coordinator.api.set_pa, self._zone_id, True
        )
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn PA off."""
        await self.hass.async_add_executor_job(
            self.coordinator.api.set_pa, self._zone_id, False
        )
        await self.coordinator.async_request_refresh()


class MonopriceDNDSwitch(CoordinatorEntity, SwitchEntity):
    """Representation of a Monoprice Do Not Disturb (DND) switch."""

    _attr_has_entity_name = True
    _attr_name = "Do Not Disturb"

    def __init__(self, coordinator, entry_id: str, zone_id: int) -> None:
        """Initialize DND switch."""
        super().__init__(coordinator)
        self._zone_id = zone_id
        self._attr_unique_id = f"{entry_id}_{zone_id}_dnd"

    @property
    def entity_registry_enabled_default(self) -> bool:
        """Only enable if zone exists or is unit 1."""
        if self._zone_id in (10, 20, 30):
            return False
        return self._zone_id < 20 or (self.coordinator.data and self._zone_id in self.coordinator.data)

    @property
    def is_on(self) -> bool | None:
        """Return true if DND is active."""
        if not self.coordinator.data or self._zone_id not in self.coordinator.data:
            return None
        return getattr(self.coordinator.data[self._zone_id], "do_not_disturb", False)

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn DND on."""
        await self.hass.async_add_executor_job(
            self.coordinator.api.set_dnd, self._zone_id, True
        )
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn DND off."""
        await self.hass.async_add_executor_job(
            self.coordinator.api.set_dnd, self._zone_id, False
        )
        await self.coordinator.async_request_refresh()
