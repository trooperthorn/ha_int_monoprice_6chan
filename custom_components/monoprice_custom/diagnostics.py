"""Diagnostics support for Monoprice 6-Zone Amplifier."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.core import HomeAssistant

from .__init__ import MonopriceConfigEntry
from .const import CONF_DEVICE_IDENTITY

TO_REDACT = {"unique_id", "port", CONF_DEVICE_IDENTITY}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: MonopriceConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    coordinator = entry.runtime_data.coordinator
    gateway = entry.runtime_data.gateway

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
        "connection": {
            "state": gateway.connection_state,
            "current_baud": gateway.current_baud_rate,
            "target_baud": coordinator.target_baud_rate,
            "active_units": coordinator.active_units,
            "last_successful_poll": (
                coordinator.last_successful_poll.isoformat()
                if coordinator.last_successful_poll
                else None
            ),
            "last_poll_duration_seconds": coordinator.last_poll_duration,
            "failure_count": gateway.failure_count,
            "reconnect_count": gateway.reconnect_count,
        },
        "zone_states": zone_data,
        "last_update_success": coordinator.last_update_success,
    }
