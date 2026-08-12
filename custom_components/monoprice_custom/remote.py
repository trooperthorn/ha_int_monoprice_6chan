from homeassistant.components.remote import RemoteEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities):
    """Set up the Monoprice remote platform."""
    coordinator = entry.runtime_data
    async_add_entities([MonopriceRemote(coordinator, entry.entry_id)])

class MonopriceRemote(CoordinatorEntity, RemoteEntity):
    """Representation of the Monoprice RS232 controller."""

    def __init__(self, coordinator, entry_id):
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry_id}_rs232_remote"
        self._attr_name = "Monoprice RS232 Controller"

    @property
    def is_on(self):
        """Always true if the integration is loaded."""
        return True

    async def async_send_command(self, command: list[str], **kwargs):
        """Send raw RS232 commands to the device."""
        for cmd in command:
            # Send raw serial write through the executor
            await self.hass.async_add_executor_job(
                self.coordinator.api.serial.write, 
                f"{cmd}\r\n".encode('ascii')
            )
