"""Support for interfacing with Monoprice 6-Zone Home Audio Controller."""

from __future__ import annotations

import logging
from typing import Any, ClassVar

from homeassistant.components.media_player import (
    MediaPlayerDeviceClass,
    MediaPlayerEntity,
    MediaPlayerEntityFeature,
    MediaPlayerState,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .__init__ import MonopriceConfigEntry
from .const import CONF_SOURCES
from .device import async_ensure_unit_devices, zone_device_info

_LOGGER = logging.getLogger(__name__)

MAX_VOLUME = 38.0


@callback
def _get_sources_from_dict(
    data: dict[str, Any],
) -> tuple[dict[int, str], dict[str, int], list[str]]:
    sources_config = data.get(CONF_SOURCES, {})
    source_id_name = {int(index): name for index, name in sources_config.items()}
    source_name_id = {v: k for k, v in source_id_name.items()}
    source_names = sorted(source_name_id.keys(), key=lambda v: source_name_id[v])
    return source_id_name, source_name_id, source_names


async def async_setup_entry(
    hass: HomeAssistant,
    entry: MonopriceConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Monoprice media player platform."""
    coordinator = entry.runtime_data.coordinator
    sources_data = entry.options if CONF_SOURCES in entry.options else entry.data
    sources = _get_sources_from_dict(sources_data)

    known_units: set[int] = set()

    def _add_units(units: set[int]) -> None:
        async_ensure_unit_devices(hass, entry.entry_id, units)
        entities = []
        for unit in sorted(units):
            entities.append(
                MonopriceZone(hass, coordinator, entry.entry_id, unit * 10, sources)
            )
            entities.extend(
                MonopriceZone(
                    hass, coordinator, entry.entry_id, unit * 10 + zone, sources
                )
                for zone in range(1, 7)
            )
        if entities:
            async_add_entities(entities)
            known_units.update(units)

    _add_units(set(coordinator.active_units))

    @callback
    def _async_add_discovered_units() -> None:
        _add_units(set(coordinator.active_units) - known_units)

    entry.async_on_unload(coordinator.async_add_listener(_async_add_discovered_units))


class MonopriceZone(CoordinatorEntity, MediaPlayerEntity):
    _attr_device_class = MediaPlayerDeviceClass.RECEIVER
    _attr_has_entity_name = True
    _attr_name = None
    _attr_sound_mode_list: ClassVar[list[str]] = [
        "Normal",
        "High Bass",
        "Medium Bass",
        "Low Bass",
    ]

    def __init__(
        self,
        hass: HomeAssistant,
        coordinator,
        entry_id: str,
        zone_id: int,
        sources: tuple[dict[int, str], dict[str, int], list[str]],
    ) -> None:
        super().__init__(coordinator)
        self._zone_id = zone_id
        self._source_id_name, self._source_name_id, self._attr_source_list = sources
        self._attr_unique_id = f"{entry_id}_{self._zone_id}"
        self._attr_device_info = zone_device_info(hass, entry_id, self._zone_id)
        self._attr_supported_features = (
            MediaPlayerEntityFeature.VOLUME_MUTE
            | MediaPlayerEntityFeature.VOLUME_SET
            | MediaPlayerEntityFeature.VOLUME_STEP
            | MediaPlayerEntityFeature.TURN_ON
            | MediaPlayerEntityFeature.TURN_OFF
            | MediaPlayerEntityFeature.SELECT_SOURCE
            | MediaPlayerEntityFeature.SELECT_SOUND_MODE
        )
        self._snapshot = None
        self._sound_mode = "Normal"

    @property
    def entity_registry_enabled_default(self) -> bool:
        """Return if entity is enabled by default."""
        return True

    @property
    def available(self) -> bool:
        """Return availability for this zone's currently detected unit."""
        return (
            super().available and self._zone_id // 10 in self.coordinator.active_units
        )

    @property
    def zone_data(self) -> Any | None:
        return (
            self.coordinator.data.get(self._zone_id) if self.coordinator.data else None
        )

    @property
    def state(self) -> MediaPlayerState | None:
        if not self.zone_data:
            return None
        return MediaPlayerState.ON if self.zone_data.power else MediaPlayerState.OFF

    @property
    def volume_level(self) -> float | None:
        return (self.zone_data.volume / MAX_VOLUME) if self.zone_data else None

    @property
    def is_volume_muted(self) -> bool | None:
        return self.zone_data.mute if self.zone_data else None

    @property
    def source(self) -> str | None:
        return (
            self._source_id_name.get(self.zone_data.source) if self.zone_data else None
        )

    @property
    def media_title(self) -> str | None:
        return self.source

    @property
    def sound_mode(self) -> str | None:
        return self._sound_mode

    async def async_turn_on(self) -> None:
        await self.coordinator.gateway.async_execute("set_power", self._zone_id, True)
        await self.coordinator.async_refresh_zone(self._zone_id)

    async def async_turn_off(self) -> None:
        await self.coordinator.gateway.async_execute("set_power", self._zone_id, False)
        await self.coordinator.async_refresh_zone(self._zone_id)

    async def async_mute_volume(self, mute: bool) -> None:
        await self.coordinator.gateway.async_execute("set_mute", self._zone_id, mute)
        await self.coordinator.async_refresh_zone(self._zone_id)

    async def async_set_volume_level(self, volume: float) -> None:
        await self.coordinator.gateway.async_execute(
            "set_volume", self._zone_id, round(volume * MAX_VOLUME)
        )
        await self.coordinator.async_refresh_zone(self._zone_id)

    async def async_volume_up(self) -> None:
        if self.volume_level is not None:
            await self.coordinator.gateway.async_execute(
                "set_volume",
                self._zone_id,
                min(round(self.volume_level * MAX_VOLUME) + 1, int(MAX_VOLUME)),
            )
            await self.coordinator.async_refresh_zone(self._zone_id)

    async def async_volume_down(self) -> None:
        if self.volume_level is not None:
            await self.coordinator.gateway.async_execute(
                "set_volume",
                self._zone_id,
                max(round(self.volume_level * MAX_VOLUME) - 1, 0),
            )
            await self.coordinator.async_refresh_zone(self._zone_id)

    async def async_select_source(self, source: str) -> None:
        if source in self._source_name_id:
            await self.coordinator.gateway.async_execute(
                "set_source", self._zone_id, self._source_name_id[source]
            )
            await self.coordinator.async_refresh_zone(self._zone_id)

    async def async_select_sound_mode(self, sound_mode: str) -> None:
        self._sound_mode = sound_mode
        bass_level = {"High Bass": 12, "Medium Bass": 10, "Low Bass": 3}.get(
            sound_mode, 7
        )
        await self.coordinator.gateway.async_execute(
            "set_bass", self._zone_id, bass_level
        )
        await self.coordinator.async_refresh_zone(self._zone_id)

    async def async_snapshot(self) -> None:
        self._snapshot = await self.coordinator.gateway.async_zone_status(self._zone_id)

    async def async_restore(self) -> None:
        if self._snapshot:
            await self.coordinator.gateway.async_execute("restore_zone", self._snapshot)
            await self.coordinator.async_refresh_zone(self._zone_id)

    async def async_set_balance(self, balance: int) -> None:
        await self.coordinator.gateway.async_execute(
            "set_balance", self._zone_id, balance
        )
        await self.coordinator.async_refresh_zone(self._zone_id)

    async def async_set_bass(self, bass: int) -> None:
        await self.coordinator.gateway.async_execute("set_bass", self._zone_id, bass)
        await self.coordinator.async_refresh_zone(self._zone_id)

    async def async_set_treble(self, treble: int) -> None:
        await self.coordinator.gateway.async_execute(
            "set_treble", self._zone_id, treble
        )
        await self.coordinator.async_refresh_zone(self._zone_id)
