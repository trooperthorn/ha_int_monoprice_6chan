"""Support for raw RS232 string execution."""
from __future__ import annotations

from homeassistant.components.remote import RemoteEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .__init__ import MonopriceConfigEntry

async def async_setup_entry(
    hass: HomeAssistant, entry: MonopriceConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up the Monoprice remote platform."""
    coordinator = entry.runtime_data.coordinator
    async_add_entities([MonopriceRemote(coordinator, entry.entry_id)])


class MonopriceRemote(CoordinatorEntity, RemoteEntity):
    """Representation of the Monoprice RS232 controller."""

    _attr_has_entity_name = True
    _attr_name = "RS232 Controller"

    def __init__(self, coordinator, entry_id: str) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry_id}_rs232"

    @property
    def is_on(self) -> bool:
        """Always true if the integration is running."""
        return True

    async def async_send_command(self, command: list[str], **kwargs) -> None:
        """Send raw RS232 commands to the device."""
        for cmd in command:
            # Ensure it ends with a carriage return as required by the manual
            if not cmd.endswith("\r"):
                cmd += "\r"
            await self.hass.async_add_executor_job(
                self.coordinator.api.serial.write, cmd.encode("ascii")
            )
