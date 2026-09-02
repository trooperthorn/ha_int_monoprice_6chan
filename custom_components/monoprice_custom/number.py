"""Support for Monoprice 6-Zone Amplifier EQ controls via number entities."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .__init__ import MonopriceConfigEntry
from .device import zone_device_info

_LOGGER = logging.getLogger(__name__)

PARALLEL_UPDATES = 1

# Wire protocol range for BS/TR is 0-14, where 0 is -7dB and 14 is +7dB
# (per the RS-232 spec and pymonoprice's ZoneStatus). We display the
# translated signed dB value to the user instead of the raw 0-14 code.
EQ_WIRE_OFFSET = 7


async def async_setup_entry(
    hass: HomeAssistant,
    entry: MonopriceConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Monoprice number entities from a config entry."""
    coordinator = entry.runtime_data.coordinator

    known_units: set[int] = set()

    def _add_units(units: set[int]) -> None:
        entities: list[MonopriceZoneNumber] = []
        for unit in sorted(units):
            for zone in range(1, 7):
                zone_id = unit * 10 + zone
                entities.extend(
                    MonopriceZoneNumber(
                        coordinator, entry.entry_id, zone_id, control_type
                    )
                    for control_type in ("Balance", "Bass", "Treble")
                )
        if entities:
            async_add_entities(entities)
            known_units.update(units)

    _add_units(set(coordinator.active_units))

    @callback
    def _async_add_discovered_units() -> None:
        _add_units(set(coordinator.active_units) - known_units)

    entry.async_on_unload(coordinator.async_add_listener(_async_add_discovered_units))


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
        self._attr_device_info = zone_device_info(entry_id, self._zone_id)

        if control_type == "Balance":
            # Wire range 0-20: 0 is full left, 10 is center, 20 is full right.
            self._attr_native_min_value = -10
            self._attr_native_max_value = 10
            self._attr_translation_key = "balance"
        elif control_type == "Bass":
            self._attr_native_min_value = -EQ_WIRE_OFFSET
            self._attr_native_max_value = EQ_WIRE_OFFSET
            self._attr_native_unit_of_measurement = "dB"
            self._attr_translation_key = "bass"
        elif control_type == "Treble":
            self._attr_native_min_value = -EQ_WIRE_OFFSET
            self._attr_native_max_value = EQ_WIRE_OFFSET
            self._attr_native_unit_of_measurement = "dB"
            self._attr_translation_key = "treble"

    @property
    def entity_registry_enabled_default(self) -> bool:
        """Return if the entity should be enabled when first added to the entity registry."""
        return self._zone_id not in (10, 20, 30)

    @property
    def available(self) -> bool:
        """Return availability for this control's currently detected unit."""
        return (
            super().available and self._zone_id // 10 in self.coordinator.active_units
        )

    @property
    def zone_data(self) -> Any | None:
        """Helper to retrieve current zone state from coordinator."""
        if not self.coordinator.data:
            return None
        return self.coordinator.data.get(self._zone_id)

    @property
    def native_value(self) -> float | None:
        """Return the current value, translated into display units."""
        if not self.zone_data:
            return None

        if self._control_type == "Balance":
            return self.zone_data.balance - 10
        if self._control_type == "Bass":
            return self.zone_data.bass - EQ_WIRE_OFFSET
        if self._control_type == "Treble":
            return self.zone_data.treble - EQ_WIRE_OFFSET
        return None

    async def async_set_native_value(self, value: float) -> None:
        """Translate the display value back to wire units and send it."""
        if self._control_type == "Balance":
            wire_value = int(value) + 10
            await self.coordinator.gateway.async_execute(
                "set_balance", self._zone_id, wire_value
            )
        elif self._control_type == "Bass":
            wire_value = int(value) + EQ_WIRE_OFFSET
            await self.coordinator.gateway.async_execute(
                "set_bass", self._zone_id, wire_value
            )
        elif self._control_type == "Treble":
            wire_value = int(value) + EQ_WIRE_OFFSET
            await self.coordinator.gateway.async_execute(
                "set_treble", self._zone_id, wire_value
            )

        await self.coordinator.async_refresh_zone(self._zone_id)
