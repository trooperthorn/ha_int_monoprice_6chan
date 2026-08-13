"""Support for interfacing with Monoprice 6-Zone Home Audio Controller."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.components.media_player import (
    MediaPlayerDeviceClass,
    MediaPlayerEntity,
    MediaPlayerEntityFeature,
    MediaPlayerState,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import config_validation as cv, entity_platform
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import ATTR_BALANCE, ATTR_BASS, ATTR_TREBLE, CONF_SOURCES, DOMAIN
from .__init__ import MonopriceConfigEntry

_LOGGER = logging.getLogger(__name__)

MAX_VOLUME = 38.0

SET_BALANCE_SCHEMA = {vol.Required(ATTR_BALANCE): vol.All(cv.positive_int, vol.Range(min=0, max=20))}
SET_BASS_SCHEMA = {vol.Required(ATTR_BASS): vol.All(cv.positive_int, vol.Range(min=0, max=14))}
SET_TREBLE_SCHEMA = {vol.Required(ATTR_TREBLE): vol.All(cv.positive_int, vol.Range(min=0, max=14))}


@callback
def _get_sources_from_dict(data: dict[str, Any]) -> tuple[dict[int, str], dict[str, int], list[str]]:
    sources_config = data.get(CONF_SOURCES, {})
    source_id_name = {int(index): name for index, name in sources_config.items()}
    source_name_id = {v: k for k, v in source_id_name.items()}
    source_names = sorted(source_name_id.keys(), key=lambda v: source_name_id[v])
    return source_id_name, source_name_id, source_names


async def async_setup_entry(
    hass: HomeAssistant, 
    entry: MonopriceConfigEntry, 
    async_add_entities: AddEntitiesCallback
) -> None:
    """Set up the Monoprice media player platform."""
    coordinator = entry.runtime_data.coordinator
    sources_data = entry.options if CONF_SOURCES in entry.options else entry.data
    sources = _get_sources_from_dict(sources_data)

    entities = []
    # Loop ONLY over detected units
    for unit in coordinator.active_units:
        # Add Master control zone for the unit (10, 20, 30)
        entities.append(MonopriceZone(coordinator, entry.entry_id, unit * 10, sources))
        # Add individual zones (11-16, 21-26, 31-36)
        for j in range(1, 7):
            entities.append(MonopriceZone(coordinator, entry.entry_id, (unit * 10) + j, sources))

    async_add_entities(entities)

    platform = entity_platform.async_get_current_platform()
    platform.async_register_entity_service("snapshot", {}, "async_snapshot")
    platform.async_register_entity_service("restore", {}, "async_restore")
    platform.async_register_entity_service("set_balance", SET_BALANCE_SCHEMA, "async_set_balance")
    platform.async_register_entity_service("set_bass", SET_BASS_SCHEMA, "async_set_bass")
    platform.async_register_entity_service("set_treble", SET_TREBLE_SCHEMA, "async_set_treble")


class MonopriceZone(CoordinatorEntity, MediaPlayerEntity):
    _attr_device_class = MediaPlayerDeviceClass.RECEIVER
    _attr_has_entity_name = True
    _attr_name = None
    _attr_sound_mode_list = ["Normal", "High Bass", "Medium Bass", "Low Bass"]

    def __init__(self, coordinator, entry_id: str, zone_id: int, sources: tuple[dict[int, str], dict[str, int], list[str]]) -> None:
        super().__init__(coordinator)
        self._zone_id = zone_id
        self._source_id_name, self._source_name_id, self._attr_source_list = sources
        self._attr_unique_id = f"{entry_id}_{self._zone_id}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{entry_id}_{self._zone_id}")},
            manufacturer="Monoprice",
            model="6-Zone Amplifier",
            name=f"Zone {self._zone_id}" if self._zone_id not in [10, 20, 30] else f"Unit {self._zone_id // 10} Master",
        )
        self._attr_supported_features = (
            MediaPlayerEntityFeature.VOLUME_MUTE | MediaPlayerEntityFeature.VOLUME_SET |
            MediaPlayerEntityFeature.VOLUME_STEP | MediaPlayerEntityFeature.TURN_ON |
            MediaPlayerEntityFeature.TURN_OFF | MediaPlayerEntityFeature.SELECT_SOURCE |
            MediaPlayerEntityFeature.SELECT_SOUND_MODE
        )
        self._snapshot = None
        self._sound_mode = "Normal"

    @property
    def entity_registry_enabled_default(self) -> bool:
        """Return if entity is enabled by default."""
        return True

    @property
    def zone_data(self) -> Any | None:
        return self.coordinator.data.get(self._zone_id) if self.coordinator.data else None

    @property
    def state(self) -> MediaPlayerState | None:
        if not self.zone_data: return None
        return MediaPlayerState.ON if self.zone_data.power else MediaPlayerState.OFF

    @property
    def volume_level(self) -> float | None:
        return (self.zone_data.volume / MAX_VOLUME) if self.zone_data else None

    @property
    def is_volume_muted(self) -> bool | None:
        return self.zone_data.mute if self.zone_data else None

    @property
    def source(self) -> str | None:
        return self._source_id_name.get(self.zone_data.source) if self.zone_data else None

    @property
    def media_title(self) -> str | None:
        return self.source

    @property
    def sound_mode(self) -> str | None:
        return self._sound_mode

    async def async_turn_on(self) -> None:
        await self.hass.async_add_executor_job(self.coordinator.api.set_power, self._zone_id, True)
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self) -> None:
        await self.hass.async_add_executor_job(self.coordinator.api.set_power, self._zone_id, False)
        await self.coordinator.async_request_refresh()

    async def async_mute_volume(self, mute: bool) -> None:
        await self.hass.async_add_executor_job(self.coordinator.api.set_mute, self._zone_id, mute)
        await self.coordinator.async_request_refresh()

    async def async_set_volume_level(self, volume: float) -> None:
        await self.hass.async_add_executor_job(self.coordinator.api.set_volume, self._zone_id, round(volume * MAX_VOLUME))
        await self.coordinator.async_request_refresh()

    async def async_volume_up(self) -> None:
        if self.volume_level is not None:
            await self.hass.async_add_executor_job(self.coordinator.api.set_volume, self._zone_id, min(round(self.volume_level * MAX_VOLUME) + 1, int(MAX_VOLUME)))
            await self.coordinator.async_request_refresh()

    async def async_volume_down(self) -> None:
        if self.volume_level is not None:
            await self.hass.async_add_executor_job(self.coordinator.api.set_volume, self._zone_id, max(round(self.volume_level * MAX_VOLUME) - 1, 0))
            await self.coordinator.async_request_refresh()

    async def async_select_source(self, source: str) -> None:
        if source in self._source_name_id:
            await self.hass.async_add_executor_job(self.coordinator.api.set_source, self._zone_id, self._source_name_id[source])
            await self.coordinator.async_request_refresh()

    async def async_select_sound_mode(self, sound_mode: str) -> None:
        self._sound_mode = sound_mode
        bass_level = {"High Bass": 12, "Medium Bass": 10, "Low Bass": 3}.get(sound_mode, 7)
        await self.hass.async_add_executor_job(self.coordinator.api.set_bass, self._zone_id, bass_level)
        await self.coordinator.async_request_refresh()

    async def async_snapshot(self) -> None:
        self._snapshot = await self.hass.async_add_executor_job(self.coordinator.api.zone_status, self._zone_id)

    async def async_restore(self) -> None:
        if self._snapshot:
            await self.hass.async_add_executor_job(self.coordinator.api.restore_zone, self._snapshot)
            await self.coordinator.async_request_refresh()

    async def async_set_balance(self, balance: int) -> None:
        await self.hass.async_add_executor_job(self.coordinator.api.set_balance, self._zone_id, balance)
        await self.coordinator.async_request_refresh()

    async def async_set_bass(self, bass: int) -> None:
        await self.hass.async_add_executor_job(self.coordinator.api.set_bass, self._zone_id, bass)
        await self.coordinator.async_request_refresh()

    async def async_set_treble(self, treble: int) -> None:
        await self.hass.async_add_executor_job(self.coordinator.api.set_treble, self._zone_id, treble)
        await self.coordinator.async_request_refresh()
