"""Diagnostics support for Monoprice 6-Zone Amplifier."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.core import HomeAssistant

from .__init__ import MonopriceConfigEntry
from .const import CONF_DEVICE_IDENTITY
from .serial import EXPANSION_PROBE_SPACING

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
            # Per-unit outcome of the last expansion probe. This path has never
            # been exercised against expansion hardware, so a field report
            # needs what each probe actually did, not just the surviving units.
            "expansion_probes": coordinator.last_discovery,
            "expansion_probe_spacing_seconds": EXPANSION_PROBE_SPACING,
            "auto_link_speed": coordinator.auto_link_speed,
            "proven_baud": gateway.proven_baud,
            "failed_baud": gateway.failed_baud,
            "last_successful_poll": (
                coordinator.last_successful_poll.isoformat()
                if coordinator.last_successful_poll
                else None
            ),
            "last_poll_duration_seconds": coordinator.last_poll_duration,
            "failure_count": gateway.failure_count,
            "reconnect_count": gateway.reconnect_count,
            # The rate the amplifier was found on before negotiation moved it.
            # A power cycle resets it to 9600 and a link fault does not, so
            # comparing this with the rate the link was on before the outage is
            # what separates the two; see outage.suspected_cause.
            "detected_baud": gateway.last_detected_baud,
        },
        "outage": {
            "online": coordinator.is_online,
            "offline_since": (
                coordinator.offline_since.isoformat()
                if coordinator.offline_since
                else None
            ),
            "last_offline_at": (
                coordinator.last_offline_at.isoformat()
                if coordinator.last_offline_at
                else None
            ),
            "last_outage_seconds": (
                round(coordinator.last_outage_duration.total_seconds())
                if coordinator.last_outage_duration
                else None
            ),
            "suspected_cause": coordinator.last_outage_cause,
            "outage_count": coordinator.outage_count,
            "consecutive_failures": coordinator.consecutive_failures,
            "retry_in_seconds": coordinator.retry_delay,
        },
        "zone_states": zone_data,
        "last_update_success": coordinator.last_update_success,
    }
