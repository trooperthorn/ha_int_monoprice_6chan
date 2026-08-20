"""Diagnostics support for Monoprice 6-Zone Amplifier."""
from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.core import HomeAssistant

from . import MonopriceConfigEntry

TO_REDACT = {"unique_id"}

async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: MonopriceConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    coordinator = entry.runtime_data.coordinator
    
    zone_data = {}
    if coordinator.data:
        for zone_id, status in coordinator.data.items():
            zone_data[f"zone_{zone_id}"] = {
                "power": status.power,
                "volume": status.volume,
                "mute": status.mute,
                "source": status.source,
                "treble": status.treble,
                "bass": status.bass,
                "balance": status.balance,
                "pa": getattr(status, "pa", False),
                "keypad": getattr(status, "keypad", False),
                "do_not_disturb": getattr(status, "do_not_disturb", False),
            }
            
    return {
        "entry": async_redact_data(entry.as_dict(), TO_REDACT),
        "zone_states": zone_data,
        "api_connected": coordinator.last_update_success,
    }
