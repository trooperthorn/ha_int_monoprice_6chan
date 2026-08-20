"""Minimal fake `homeassistant` package tree.

The real `homeassistant` package can't be installed in every environment
(its full extras closure pulls in hardware-specific dependencies that don't
build everywhere). These stubs implement just enough of the surface
`coordinator.py` and `config_flow.py` touch at import time and at runtime so
their actual logic - baud negotiation, active-unit discovery, zone-refresh
merging, port labeling, source parsing - can be exercised with real behavior
instead of mocked out.

This is not a substitute for `pytest-homeassistant-custom-component`, which
verifies against the real framework (config entry lifecycle, entity
registry, translations, etc.). Install that separately for full-framework
coverage; see README "Testing".
"""
from __future__ import annotations

import sys
import types
from typing import Any, Callable


def _module(name: str) -> types.ModuleType:
    mod = types.ModuleType(name)
    sys.modules[name] = mod
    return mod


def install() -> None:
    """Register fake `homeassistant.*` modules in sys.modules, once."""
    if "homeassistant" in sys.modules:
        return

    ha = _module("homeassistant")
    ha.__path__ = []  # mark as a package

    # -- homeassistant.core --------------------------------------------
    core = _module("homeassistant.core")

    class HomeAssistant:
        """Stand-in for the real HomeAssistant object; tests replace this."""

    def callback(func: Callable[..., Any]) -> Callable[..., Any]:
        return func

    core.HomeAssistant = HomeAssistant
    core.callback = callback

    # -- homeassistant.const --------------------------------------------
    const = _module("homeassistant.const")
    const.CONF_PORT = "port"

    class Platform:
        MEDIA_PLAYER = "media_player"
        SWITCH = "switch"
        SENSOR = "sensor"
        NUMBER = "number"
        TEXT = "text"
        REMOTE = "remote"

    const.Platform = Platform

    class EntityCategory:
        DIAGNOSTIC = "diagnostic"
        CONFIG = "config"

    const.EntityCategory = EntityCategory

    # -- homeassistant.exceptions ----------------------------------------
    exceptions = _module("homeassistant.exceptions")

    class HomeAssistantError(Exception):
        pass

    class ConfigEntryNotReady(HomeAssistantError):
        pass

    exceptions.HomeAssistantError = HomeAssistantError
    exceptions.ConfigEntryNotReady = ConfigEntryNotReady

    # -- homeassistant.config_entries ------------------------------------
    config_entries = _module("homeassistant.config_entries")

    class ConfigEntry:
        def __init__(self) -> None:
            self.data: dict[str, Any] = {}
            self.options: dict[str, Any] = {}
            self.entry_id = "test_entry_id"
            self.runtime_data: Any = None

        def __class_getitem__(cls, item: Any) -> type:
            return cls

    SOURCE_RECONFIGURE = "reconfigure"

    class ConfigFlow:
        def __init_subclass__(cls, domain: str | None = None, **kwargs: Any) -> None:
            cls._domain = domain

        def __init__(self) -> None:
            self.hass: Any = None
            self.source: str | None = None

        def async_show_form(self, **kwargs: Any) -> dict[str, Any]:
            return {"type": "form", **kwargs}

        def async_create_entry(self, **kwargs: Any) -> dict[str, Any]:
            return {"type": "create_entry", **kwargs}

        def async_update_reload_and_abort(self, entry: Any, **kwargs: Any) -> dict[str, Any]:
            return {"type": "abort", "reason": "reconfigure_successful", **kwargs}

        def _get_reconfigure_entry(self) -> Any:
            return self._reconfigure_entry

    class OptionsFlow:
        def __init__(self) -> None:
            self.config_entry: Any = None

        def async_show_form(self, **kwargs: Any) -> dict[str, Any]:
            return {"type": "form", **kwargs}

        def async_create_entry(self, **kwargs: Any) -> dict[str, Any]:
            return {"type": "create_entry", **kwargs}

    ConfigFlowResult = dict

    config_entries.ConfigEntry = ConfigEntry
    config_entries.ConfigFlow = ConfigFlow
    config_entries.OptionsFlow = OptionsFlow
    config_entries.ConfigFlowResult = ConfigFlowResult
    config_entries.SOURCE_RECONFIGURE = SOURCE_RECONFIGURE

    # -- homeassistant.helpers -------------------------------------------
    helpers = _module("homeassistant.helpers")
    helpers.__path__ = []

    selector = _module("homeassistant.helpers.selector")

    class SelectSelectorConfig:
        def __init__(self, **kwargs: Any) -> None:
            self.__dict__.update(kwargs)

    class SelectSelectorMode:
        DROPDOWN = "dropdown"

    class SelectSelector:
        def __init__(self, config: Any) -> None:
            self.config = config

    selector.SelectSelector = SelectSelector
    selector.SelectSelectorConfig = SelectSelectorConfig
    selector.SelectSelectorMode = SelectSelectorMode

    update_coordinator = _module("homeassistant.helpers.update_coordinator")

    class UpdateFailed(Exception):
        pass

    class DataUpdateCoordinator:
        def __init__(self, hass: Any, logger: Any, name: str = "", update_interval: Any = None) -> None:
            self.hass = hass
            self.logger = logger
            self.name = name
            self.update_interval = update_interval
            self.data: Any = None
            self.last_update_success = True

        async def async_config_entry_first_refresh(self) -> None:
            self.data = await self._async_update_data()

        async def async_request_refresh(self) -> None:
            self.data = await self._async_update_data()

        def async_set_updated_data(self, data: Any) -> None:
            self.data = data

    class CoordinatorEntity:
        def __init__(self, coordinator: Any) -> None:
            self.coordinator = coordinator

    update_coordinator.DataUpdateCoordinator = DataUpdateCoordinator
    update_coordinator.UpdateFailed = UpdateFailed
    update_coordinator.CoordinatorEntity = CoordinatorEntity

    device_registry = _module("homeassistant.helpers.device_registry")

    class DeviceInfo(dict):
        def __init__(self, **kwargs: Any) -> None:
            super().__init__(**kwargs)

    device_registry.DeviceInfo = DeviceInfo

    entity_platform = _module("homeassistant.helpers.entity_platform")
    entity_platform.AddEntitiesCallback = Callable

    def async_get_current_platform() -> Any:
        raise RuntimeError("not available outside a running platform setup")

    entity_platform.async_get_current_platform = async_get_current_platform

    config_validation = _module("homeassistant.helpers.config_validation")
    config_validation.positive_int = int

    helpers.selector = selector
    helpers.update_coordinator = update_coordinator
    helpers.device_registry = device_registry
    helpers.entity_platform = entity_platform
    helpers.config_validation = config_validation

    ha.core = core
    ha.const = const
    ha.exceptions = exceptions
    ha.config_entries = config_entries
    ha.helpers = helpers
