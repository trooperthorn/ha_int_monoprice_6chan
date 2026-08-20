"""The Monoprice 6-Zone Amplifier integration."""
import logging
from dataclasses import dataclass
from typing import TypeAlias

from serial import SerialException

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PORT
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady

from .api import get_monoprice_extended
from .const import CONF_NOT_FIRST_RUN, DOMAIN, FIRST_RUN, PLATFORMS
from .coordinator import MonopriceCoordinator

_LOGGER = logging.getLogger(__name__)


@dataclass
class MonopriceData:
    """Class to hold runtime data for the Monoprice integration."""
    coordinator: MonopriceCoordinator
    first_run: bool

MonopriceConfigEntry: TypeAlias = ConfigEntry[MonopriceData]


async def async_setup_entry(hass: HomeAssistant, entry: MonopriceConfigEntry) -> bool:
    """Set up Monoprice 6-Zone Amplifier from a config entry."""
    port = entry.data[CONF_PORT]

    try:
        # Spin up the synchronous serial connection in the executor
        monoprice = await hass.async_add_executor_job(get_monoprice_extended, port)
    except SerialException as err:
        _LOGGER.error("Error connecting to Monoprice controller at %s", port)
        raise ConfigEntryNotReady from err

    # Initialize the coordinator
    coordinator = MonopriceCoordinator(hass, monoprice, entry)

    # Fetch initial state before loading platforms so entities don't boot as "Unavailable"
    await coordinator.async_config_entry_first_refresh()

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
        first_run=first_run
    )

    # Load all defined platforms
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: MonopriceConfigEntry) -> bool:
    """Unload a config entry."""
    # The undo_listener and hass.data.pop() logic is no longer needed.
    # async_on_unload handles the listener, and runtime_data is destroyed automatically.
    return bool(await hass.config_entries.async_unload_platforms(entry, PLATFORMS))


async def _update_listener(hass: HomeAssistant, entry: MonopriceConfigEntry) -> None:
    """Handle options update."""
    await hass.config_entries.async_reload(entry.entry_id)
