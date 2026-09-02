"""Support for raw RS232 string execution."""

from __future__ import annotations

import voluptuous as vol
from homeassistant.components.remote import RemoteEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_platform
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .__init__ import MonopriceConfigEntry
from .const import ATTR_BAUD_RATE, CONF_BAUD_RATE
from .device import controller_device_info
from .serial import SUPPORTED_BAUD_RATES

SET_BAUD_RATE_SCHEMA = {vol.Required(ATTR_BAUD_RATE): vol.In(SUPPORTED_BAUD_RATES)}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: MonopriceConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Monoprice remote platform."""
    coordinator = entry.runtime_data.coordinator
    async_add_entities([MonopriceRemote(coordinator, entry.entry_id)])

    platform = entity_platform.async_get_current_platform()
    platform.async_register_entity_service(
        "set_baud_rate", SET_BAUD_RATE_SCHEMA, "async_set_baud_rate"
    )


class MonopriceRemote(CoordinatorEntity, RemoteEntity):
    """Representation of the Monoprice RS232 controller."""

    _attr_has_entity_name = True
    _attr_name = "RS232 Controller"

    def __init__(self, coordinator, entry_id: str) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry_id}_rs232"
        self._attr_device_info = controller_device_info(entry_id)

    @property
    def is_on(self) -> bool:
        """Always true if the integration is running."""
        return True

    async def async_send_command(self, command: list[str], **kwargs) -> None:
        """Send raw RS232 commands to the device, serialized against polling."""
        for cmd in command:
            await self.coordinator.gateway.async_execute("send_raw", cmd)

    async def async_set_baud_rate(self, baud_rate: int) -> None:
        """Negotiate the amplifier and local port to a new link speed."""
        await self.coordinator.gateway.async_ensure_link(baud_rate)
        self.hass.config_entries.async_update_entry(
            self.coordinator.entry,
            options={
                **self.coordinator.entry.options,
                CONF_BAUD_RATE: baud_rate,
            },
        )
