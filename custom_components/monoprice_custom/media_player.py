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
from .const import (
    CONF_ALL_ON_VOLUME,
    CONF_IGNORE_ZONES,
    CONF_MAX_VOLUME,
    CONF_PORT,
    CONF_SOURCES,
    CONF_ZONE_NAMES,
    DEFAULT_ALL_ON_VOLUME,
    DEFAULT_MAX_VOLUME,
)
from .device import async_ensure_unit_devices, zone_device_info
from .zones import is_master, write_targets

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
    port = entry.data[CONF_PORT]
    sources_data = entry.options if CONF_SOURCES in entry.options else entry.data
    sources = _get_sources_from_dict(sources_data)
    zone_names = entry.options.get(CONF_ZONE_NAMES, {})

    known_units: set[int] = set()

    def _add_units(units: set[int]) -> None:
        async_ensure_unit_devices(hass, entry.entry_id, units)
        entities = []
        for unit in sorted(units):
            for zone_id in (unit * 10, *(unit * 10 + zone for zone in range(1, 7))):
                _LOGGER.debug("Adding zone %d for port %s", zone_id, port)
                entities.append(
                    MonopriceZone(
                        hass, coordinator, entry.entry_id, zone_id, sources, zone_names
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
        zone_names: dict[str, str] | None = None,
    ) -> None:
        super().__init__(coordinator)
        self._zone_id = zone_id
        self._source_id_name, self._source_name_id, self._attr_source_list = sources
        self._attr_unique_id = f"{entry_id}_{self._zone_id}"
        custom_name = (zone_names or {}).get(str(zone_id))
        self._attr_device_info = zone_device_info(
            hass, entry_id, self._zone_id, custom_name
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

    @property
    def _options(self) -> dict[str, Any]:
        return self.coordinator.entry.options

    @property
    def _is_master(self) -> bool:
        """Whether this entity is a unit's broadcast (N0) address."""
        return is_master(self._zone_id)

    @property
    def _max_volume(self) -> int:
        """Return the configured volume ceiling, clamped to the wire range."""
        try:
            configured = int(self._options.get(CONF_MAX_VOLUME, DEFAULT_MAX_VOLUME))
        except (TypeError, ValueError):
            return DEFAULT_MAX_VOLUME
        return max(1, min(configured, int(MAX_VOLUME)))

    @property
    def _all_on_volume(self) -> int:
        """Return the volume forced on a master power-on, or 0 when disabled."""
        try:
            configured = int(
                self._options.get(CONF_ALL_ON_VOLUME, DEFAULT_ALL_ON_VOLUME)
            )
        except (TypeError, ValueError):
            return DEFAULT_ALL_ON_VOLUME
        return max(0, min(configured, self._max_volume))

    def _capped(self, volume: int) -> int:
        """Clamp a wire volume to the configured ceiling."""
        return max(0, min(volume, self._max_volume))

    async def _async_send(
        self, method: str, *args: Any, honour_exclusions: bool = True
    ) -> None:
        """Send a command to every zone this entity addresses."""
        for zone_id in write_targets(
            self._zone_id,
            self._options.get(CONF_IGNORE_ZONES),
            honour_exclusions=honour_exclusions,
        ):
            await self.coordinator.gateway.async_execute(method, zone_id, *args)

    async def async_turn_on(self) -> None:
        await self._async_send("set_power", True)
        # Writes only stick while a zone is on, so the guard volume follows the
        # power-on rather than preceding it; see docs/protocol.md.
        if self._is_master and (safe := self._all_on_volume):
            await self._async_send("set_volume", safe)
        await self.coordinator.async_refresh_zone(self._zone_id)

    async def async_turn_off(self) -> None:
        # All-off reaches every zone, excluded ones included: an exclusion is
        # about not being switched on or re-sourced, not about being left on.
        await self._async_send("set_power", False, honour_exclusions=False)
        await self.coordinator.async_refresh_zone(self._zone_id)

    async def async_mute_volume(self, mute: bool) -> None:
        await self._async_send("set_mute", mute)
        await self.coordinator.async_refresh_zone(self._zone_id)

    async def async_set_volume_level(self, volume: float) -> None:
        await self._async_send("set_volume", self._capped(round(volume * MAX_VOLUME)))
        await self.coordinator.async_refresh_zone(self._zone_id)

    async def async_volume_up(self) -> None:
        if self.volume_level is not None:
            await self._async_send(
                "set_volume",
                self._capped(round(self.volume_level * MAX_VOLUME) + 1),
            )
            await self.coordinator.async_refresh_zone(self._zone_id)

    async def async_volume_down(self) -> None:
        if self.volume_level is not None:
            await self._async_send(
                "set_volume",
                max(round(self.volume_level * MAX_VOLUME) - 1, 0),
            )
            await self.coordinator.async_refresh_zone(self._zone_id)

    async def async_select_source(self, source: str) -> None:
        if source in self._source_name_id:
            await self._async_send("set_source", self._source_name_id[source])
            await self.coordinator.async_refresh_zone(self._zone_id)

    async def async_select_sound_mode(self, sound_mode: str) -> None:
        self._sound_mode = sound_mode
        bass_level = {"High Bass": 12, "Medium Bass": 10, "Low Bass": 3}.get(
            sound_mode, 7
        )
        await self._async_send("set_bass", bass_level)
        await self.coordinator.async_refresh_zone(self._zone_id)

    async def async_snapshot(self) -> None:
        # A master id has no readable record of its own, so snapshot the zone
        # its state already mirrors rather than querying `?N0`.
        query_id = self._zone_id + 1 if self._is_master else self._zone_id
        self._snapshot = await self.coordinator.gateway.async_zone_status(query_id)

    async def async_restore(self) -> None:
        if self._snapshot:
            await self.coordinator.gateway.async_execute("restore_zone", self._snapshot)
            await self.coordinator.async_refresh_zone(self._zone_id)

    async def async_set_balance(self, balance: int) -> None:
        await self._async_send("set_balance", balance)
        await self.coordinator.async_refresh_zone(self._zone_id)

    async def async_set_bass(self, bass: int) -> None:
        await self._async_send("set_bass", bass)
        await self.coordinator.async_refresh_zone(self._zone_id)

    async def async_set_treble(self, treble: int) -> None:
        await self._async_send("set_treble", treble)
        await self.coordinator.async_refresh_zone(self._zone_id)
