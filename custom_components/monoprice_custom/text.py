"""Support for renaming Monoprice Keypad LCD screens."""
from __future__ import annotations

from homeassistant.components.text import TextEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .__init__ import MonopriceConfigEntry
from .const import DOMAIN

async def async_setup_entry(
    hass: HomeAssistant, entry: MonopriceConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up Monoprice text entities."""
    coordinator = entry.runtime_data.coordinator
    
    entities = [
        MonopriceKeypadText(coordinator, entry.entry_id, i, f"Source {i} Display Name") 
        for i in range(1, 7)
    ]
    
    # The 'M' command sets the boot welcome message on the keypad
    entities.append(MonopriceKeypadText(coordinator, entry.entry_id, "M", "Keypad Welcome Message"))

    async_add_entities(entities)


class MonopriceKeypadText(CoordinatorEntity, TextEntity):
    """Representation of the physical Keypad LCD display strings."""
    
    _attr_has_entity_name = True
    _attr_native_max = 8 # The hardware strictly limits this to 8 characters

    def __init__(self, coordinator, entry_id: str, command_id: int | str, name: str) -> None:
        super().__init__(coordinator)
        self._command_id = command_id
        self._attr_name = name
        self._attr_unique_id = f"{entry_id}_text_{command_id}"
        self._attr_native_value = "" # State is write-only in the hardware

    async def async_set_value(self, value: str) -> None:
        """Send the renaming string to the RS232 port."""
        if len(value) > 8:
            value = value[:8]
            
        # Pad with spaces if less than 8 characters
        padded_value = value.ljust(8)
        command = f"{self._command_id}<{padded_value}\r".encode("ascii")

        await self.hass.async_add_executor_job(
            self.coordinator.api.serial.write, command
        )
        self._attr_native_value = value
        self.async_write_ha_state()
