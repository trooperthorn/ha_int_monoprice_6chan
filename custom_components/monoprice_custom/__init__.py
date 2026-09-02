"""The Monoprice 6-Zone Amplifier integration."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TypeAlias

import serialx
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PORT
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady

from .api import get_monoprice_extended
from .const import (
    CONF_BAUD_RATE,
    CONF_DEVICE_IDENTITY,
    CONF_IDENTITY_KIND,
    CONF_LAST_KNOWN_BAUD,
    CONF_NOT_FIRST_RUN,
    CONF_SOURCES,
    PLATFORMS,
)
from .coordinator import MonopriceCoordinator
from .gateway import MonopriceGateway
from .serial import POWER_ON_BAUD_RATE, canonicalize_endpoint, endpoint_identity

_LOGGER = logging.getLogger(__name__)


@dataclass
class MonopriceData:
    """Class to hold runtime data for the Monoprice integration."""

    coordinator: MonopriceCoordinator
    gateway: MonopriceGateway
    first_run: bool


MonopriceConfigEntry: TypeAlias = ConfigEntry[MonopriceData]


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Migrate version 1 ownership into version 2 data and options."""
    if entry.version > 2:
        return False
    if entry.version == 2:
        return True

    port = canonicalize_endpoint(entry.data[CONF_PORT])
    identity = endpoint_identity(port)
    data = {
        **entry.data,
        CONF_PORT: port,
        CONF_DEVICE_IDENTITY: identity.key,
        CONF_IDENTITY_KIND: identity.kind,
        CONF_LAST_KNOWN_BAUD: int(
            entry.options.get(CONF_BAUD_RATE, POWER_ON_BAUD_RATE)
        ),
    }
    legacy_sources = data.pop(CONF_SOURCES, {})
    options = {
        **entry.options,
        CONF_SOURCES: entry.options.get(CONF_SOURCES, legacy_sources),
        CONF_BAUD_RATE: int(entry.options.get(CONF_BAUD_RATE, POWER_ON_BAUD_RATE)),
    }
    hass.config_entries.async_update_entry(
        entry,
        data=data,
        options=options,
        unique_id=entry.unique_id or identity.key,
        version=2,
    )
    return True


async def async_setup_entry(hass: HomeAssistant, entry: MonopriceConfigEntry) -> bool:
    """Set up Monoprice 6-Zone Amplifier from a config entry."""
    port = entry.data[CONF_PORT]

    try:
        # Spin up the synchronous serial connection in the executor
        monoprice = await hass.async_add_executor_job(get_monoprice_extended, port)
    except (serialx.SerialException, PermissionError, OSError) as err:
        _LOGGER.error("Error connecting to Monoprice controller at %s", port)
        raise ConfigEntryNotReady from err

    gateway = MonopriceGateway(
        hass,
        monoprice,
        int(entry.data.get(CONF_LAST_KNOWN_BAUD, POWER_ON_BAUD_RATE)),
    )
    coordinator = MonopriceCoordinator(hass, gateway, entry)

    try:
        # Fetch initial state before entities are created. Any setup failure must
        # release the interface so a retry or reconfigure can open it.
        await coordinator.async_config_entry_first_refresh()
    except Exception:
        await coordinator.async_shutdown()
        await gateway.async_close()
        raise

    # double negative to handle absence of value
    first_run = not bool(entry.data.get(CONF_NOT_FIRST_RUN))

    if first_run:
        hass.config_entries.async_update_entry(
            entry, data={**entry.data, CONF_NOT_FIRST_RUN: True}
        )

    # Modern listener registration - HA automatically cleans this up on unload
    entry.async_on_unload(entry.add_update_listener(_update_listener))

    # Platinum standard: Use entry.runtime_data instead of hass.data
    entry.runtime_data = MonopriceData(
        coordinator=coordinator,
        gateway=gateway,
        first_run=first_run,
    )

    try:
        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    except Exception:
        await coordinator.async_shutdown()
        await gateway.async_close()
        raise

    return True


async def async_unload_entry(hass: HomeAssistant, entry: MonopriceConfigEntry) -> bool:
    """Unload a config entry."""
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if not unloaded:
        return False

    await entry.runtime_data.coordinator.async_shutdown()
    await entry.runtime_data.gateway.async_close()
    return True


async def _update_listener(hass: HomeAssistant, entry: MonopriceConfigEntry) -> None:
    """Handle options update."""
    await hass.config_entries.async_reload(entry.entry_id)
