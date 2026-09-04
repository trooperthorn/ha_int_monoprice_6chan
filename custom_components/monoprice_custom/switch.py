"""Support for Monoprice 6-Zone Amplifier switches."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .__init__ import MonopriceConfigEntry
from .device import async_ensure_unit_devices, zone_device_info

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: MonopriceConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Monoprice switch entities."""
    coordinator = entry.runtime_data.coordinator

    known_units: set[int] = set()

    def _add_units(units: set[int]) -> None:
        async_ensure_unit_devices(hass, entry.entry_id, units)
        entities: list[MonopricePASwitch | MonopriceDNDSwitch] = []
        for unit in sorted(units):
            master_id = unit * 10
            entities.extend(
                (
                    MonopricePASwitch(
                        hass, coordinator, entry.entry_id, master_id, is_master=True
                    ),
                    MonopriceDNDSwitch(
                        hass, coordinator, entry.entry_id, master_id, is_master=True
                    ),
                )
            )
            for zone in range(1, 7):
                zone_id = unit * 10 + zone
                entities.extend(
                    (
                        MonopricePASwitch(hass, coordinator, entry.entry_id, zone_id),
                        MonopriceDNDSwitch(hass, coordinator, entry.entry_id, zone_id),
                    )
                )
        if entities:
            async_add_entities(entities)
            known_units.update(units)

    _add_units(set(coordinator.active_units))

    @callback
    def _async_add_discovered_units() -> None:
        _add_units(set(coordinator.active_units) - known_units)

    entry.async_on_unload(coordinator.async_add_listener(_async_add_discovered_units))


class MonopricePASwitch(CoordinatorEntity, SwitchEntity):
    """Public Address (PA) toggle switch."""

    _attr_has_entity_name = True

    def __init__(
        self,
        hass: HomeAssistant,
        coordinator,
        entry_id: str,
        zone_id: int,
        is_master: bool = False,
    ) -> None:
        """Initialize PA switch."""
        super().__init__(coordinator)
        self._zone_id = zone_id
        self._is_master = is_master

        # Keep entity name simple so it appends cleanly to Device Name
        self._attr_name = "PA" if is_master else "Public Address"
        self._attr_translation_key = "pa_switch"
        self._attr_unique_id = f"{entry_id}_{zone_id}_pa_switch"
        self._attr_device_info = zone_device_info(hass, entry_id, zone_id)

    @property
    def entity_registry_enabled_default(self) -> bool:
        """Enable by default."""
        return True

    @property
    def available(self) -> bool:
        """Return availability for this switch's currently detected unit."""
        return (
            super().available and self._zone_id // 10 in self.coordinator.active_units
        )

    @property
    def is_on(self) -> bool | None:
        """Return True if PA is active."""
        if not self.coordinator.data or self._zone_id not in self.coordinator.data:
            return None
        return getattr(self.coordinator.data[self._zone_id], "pa", False)

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn PA on."""
        await self.coordinator.gateway.async_execute("set_pa", self._zone_id, True)
        await self.coordinator.async_refresh_zone(self._zone_id)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn PA off."""
        await self.coordinator.gateway.async_execute("set_pa", self._zone_id, False)
        await self.coordinator.async_refresh_zone(self._zone_id)


class MonopriceDNDSwitch(CoordinatorEntity, SwitchEntity):
    """Do Not Disturb (DND) toggle switch."""

    _attr_has_entity_name = True

    def __init__(
        self,
        hass: HomeAssistant,
        coordinator,
        entry_id: str,
        zone_id: int,
        is_master: bool = False,
    ) -> None:
        """Initialize DND switch."""
        super().__init__(coordinator)
        self._zone_id = zone_id
        self._is_master = is_master

        self._attr_name = "Master DND" if is_master else "Do Not Disturb"
        self._attr_translation_key = "dnd_switch"
        self._attr_unique_id = f"{entry_id}_{zone_id}_dnd_switch"
        self._attr_device_info = zone_device_info(hass, entry_id, zone_id)

    @property
    def entity_registry_enabled_default(self) -> bool:
        """Enable by default."""
        return True

    @property
    def available(self) -> bool:
        """Return availability for this switch's currently detected unit."""
        return (
            super().available and self._zone_id // 10 in self.coordinator.active_units
        )

    @property
    def is_on(self) -> bool | None:
        """Return True if DND is active."""
        if not self.coordinator.data or self._zone_id not in self.coordinator.data:
            return None
        return getattr(self.coordinator.data[self._zone_id], "do_not_disturb", False)

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn DND on."""
        await self.coordinator.gateway.async_execute("set_dnd", self._zone_id, True)
        await self.coordinator.async_refresh_zone(self._zone_id)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn DND off."""
        await self.coordinator.gateway.async_execute("set_dnd", self._zone_id, False)
        await self.coordinator.async_refresh_zone(self._zone_id)
