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

from .const import (
    ATTR_BALANCE,
    ATTR_BASS,
    ATTR_TREBLE,
    CONF_SOURCES,
    DOMAIN,
)
from .__init__ import MonopriceConfigEntry

_LOGGER = logging.getLogger(__name__)

MAX_VOLUME = 38.0

# Schemas for custom entity services
SET_BALANCE_SCHEMA = {
    vol.Required(ATTR_BALANCE): vol.All(cv.positive_int, vol.Range(min=0, max=20))
}

SET_BASS_SCHEMA = {
    vol.Required(ATTR_BASS): vol.All(cv.positive_int, vol.Range(min=0, max=14))
}

SET_TREBLE_SCHEMA = {
    vol.Required(ATTR_TREBLE): vol.All(cv.positive_int, vol.Range(min=0, max=14))
}


@callback
def _get_sources_from_dict(data: dict[str, Any]) -> tuple[dict[int, str], dict[str, int], list[str]]:
    """Format configured source dictionaries."""
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
    """Set up the Monoprice 6-zone amplifier platform."""
    monoprice_data = entry.runtime_data
    coordinator = monoprice_data.coordinator

    # Retrieve sources configuration
    sources_data = entry.options if CONF_SOURCES in entry.options else entry.data
    sources = _get_sources_from_dict(sources_data)

    # Support up to 3 stacked units: Unit 1 (11-16), Unit 2 (21-26), Unit 3 (31-36)
    # Plus Master Zone controllers (10, 20, 30)
    entities = []
    for i in range(1, 4):
        # Add Master zone for unit (10, 20, 30)
        entities.append(MonopriceZone(coordinator, entry.entry_id, i * 10, sources))
        # Add individual zones (11-16, 21-26, 31-36)
        for j in range(1, 7):
            zone_id = (i * 10) + j
            entities.append(MonopriceZone(coordinator, entry.entry_id, zone_id, sources))

    async_add_entities(entities)

    # Register entity services for custom actions
    platform = entity_platform.async_get_current_platform()
    
    platform.async_register_entity_service("snapshot", {}, "async_snapshot")
    platform.async_register_entity_service("restore", {}, "async_restore")
    platform.async_register_entity_service("set_balance", SET_BALANCE_SCHEMA, "async_set_balance")
    platform.async_register_entity_service("set_bass", SET_BASS_SCHEMA, "async_set_bass")
    platform.async_register_entity_service("set_treble", SET_TREBLE_SCHEMA, "async_set_treble")


class MonopriceZone(CoordinatorEntity, MediaPlayerEntity):
    """Representation of a Monoprice amplifier zone."""

    _attr_device_class = MediaPlayerDeviceClass.RECEIVER
    _attr_has_entity_name = True
    _attr_name = None
    _attr_sound_mode_list = ["Normal", "High Bass", "Medium Bass", "Low Bass"]

    def __init__(
        self,
        coordinator,
        entry_id: str,
        zone_id: int,
        sources: tuple[dict[int, str], dict[str, int], list[str]],
    ) -> None:
        """Initialize new zone."""
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
        """Return if entity is enabled by default when first added."""
        # Disable master control zones (10, 20, 30) by default
        if self._zone_id in (10, 20, 30):
            return False
        # Enable Unit 1 by default; enable Units 2 & 3 only if hardware responds
        return self._zone_id < 20 or (self.zone_data is not None)

    @property
    def zone_data(self) -> Any | None:
        """Helper to get current zone status from coordinator."""
        if self.coordinator.data is None:
            return None
        return self.coordinator.data.get(self._zone_id)

    @property
    def state(self) -> MediaPlayerState | None:
        """Return the power state of the zone."""
        if not self.zone_data:
            return None
        return MediaPlayerState.ON if self.zone_data.power else MediaPlayerState.OFF

    @property
    def volume_level(self) -> float | None:
        """Return the volume level of the zone (0.0 to 1.0)."""
        if not self.zone_data:
            return None
        return self.zone_data.volume / MAX_VOLUME

    @property
    def is_volume_muted(self) -> bool | None:
        """Return boolean if volume is muted."""
        if not self.zone_data:
            return None
        return self.zone_data.mute

    @property
    def source(self) -> str | None:
        """Return the current input source."""
        if not self.zone_data:
            return None
        return self._source_id_name.get(self.zone_data.source)

    @property
    def media_title(self) -> str | None:
        """Return the current source as media title."""
        return self.source

    @property
    def sound_mode(self) -> str | None:
        """Return the current sound mode."""
        return self._sound_mode

    async def async_turn_on(self) -> None:
        """Turn the media player on."""
        await self.hass.async_add_executor_job(
            self.coordinator.api.set_power, self._zone_id, True
        )
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self) -> None:
        """Turn the media player off."""
        await self.hass.async_add_executor_job(
            self.coordinator.api.set_power, self._zone_id, False
        )
        await self.coordinator.async_request_refresh()

    async def async_mute_volume(self, mute: bool) -> None:
        """Mute (true) or unmute (false) media player."""
        await self.hass.async_add_executor_job(
            self.coordinator.api.set_mute, self._zone_id, mute
        )
        await self.coordinator.async_request_refresh()

    async def async_set_volume_level(self, volume: float) -> None:
        """Set volume level, range 0..1."""
        target_vol = round(volume * MAX_VOLUME)
        await self.hass.async_add_executor_job(
            self.coordinator.api.set_volume, self._zone_id, target_vol
        )
        await self.coordinator.async_request_refresh()

    async def async_volume_up(self) -> None:
        """Volume up the media player."""
        if self.volume_level is None:
            return
        current_vol = round(self.volume_level * MAX_VOLUME)
        await self.hass.async_add_executor_job(
            self.coordinator.api.set_volume, self._zone_id, min(current_vol + 1, int(MAX_VOLUME))
        )
        await self.coordinator.async_request_refresh()

    async def async_volume_down(self) -> None:
        """Volume down media player."""
        if self.volume_level is None:
            return
        current_vol = round(self.volume_level * MAX_VOLUME)
        await self.hass.async_add_executor_job(
            self.coordinator.api.set_volume, self._zone_id, max(current_vol - 1, 0)
        )
        await self.coordinator.async_request_refresh()

    async def async_select_source(self, source: str) -> None:
        """Select input source."""
        if source not in self._source_name_id:
            return
        idx = self._source_name_id[source]
        await self.hass.async_add_executor_job(
            self.coordinator.api.set_source, self._zone_id, idx
        )
        await self.coordinator.async_request_refresh()

    async def async_select_sound_mode(self, sound_mode: str) -> None:
        """Switch the sound mode preset."""
        self._sound_mode = sound_mode
        bass_level = 7
        if sound_mode == "High Bass":
            bass_level = 12
        elif sound_mode == "Medium Bass":
            bass_level = 10
        elif sound_mode == "Low Bass":
            bass_level = 3

        await self.hass.async_add_executor_job(
            self.coordinator.api.set_bass, self._zone_id, bass_level
        )
        await self.coordinator.async_request_refresh()

    # --- Custom Entity Services ---

    async def async_snapshot() -> None:
        """Save zone's current state."""
        self._snapshot = await self.hass.async_add_executor_job(
            self.coordinator.api.zone_status, self._zone_id
        )

    async def async_restore() -> None:
        """Restore saved state."""
        if self._snapshot:
            await self.hass.async_add_executor_job(
                self.coordinator.api.restore_zone, self._snapshot
            )
            await self.coordinator.async_request_refresh()

    async def async_set_balance(self, balance: int) -> None:
        """Set balance level (0-20)."""
        await self.hass.async_add_executor_job(
            self.coordinator.api.set_balance, self._zone_id, balance
        )
        await self.coordinator.async_request_refresh()

    async def async_set_bass(self, bass: int) -> None:
        """Set bass level (0-14)."""
        await self.hass.async_add_executor_job(
            self.coordinator.api.set_bass, self._zone_id, bass
        )
        await self.coordinator.async_request_refresh()

    async def async_set_treble(self, treble: int) -> None:
        """Set treble level (0-14)."""
        await self.hass.async_add_executor_job(
            self.coordinator.api.set_treble, self._zone_id, treble
        )
        await self.coordinator.async_request_refresh()
