"""Shared device-registry helpers for the Monoprice integration.

Models the real hardware hierarchy - controller -> main unit -> zone -
via `via_device`, instead of each zone being an unrelated flat device.
"""
from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo

from .const import DOMAIN


def controller_device_info(entry_id: str) -> DeviceInfo:
    """Device representing the RS-232 link/integration itself."""
    return DeviceInfo(
        identifiers={(DOMAIN, entry_id)},
        manufacturer="Monoprice",
        model="6-Zone Amplifier RS-232 Controller",
        name="Monoprice Controller",
    )


def unit_device_info(entry_id: str, unit: int) -> DeviceInfo:
    """Device representing one main unit (10/20/30), linked to the controller."""
    return DeviceInfo(
        identifiers={(DOMAIN, f"{entry_id}_{unit * 10}")},
        manufacturer="Monoprice",
        model="6-Zone Amplifier",
        name=f"Unit {unit} Master",
        via_device=(DOMAIN, entry_id),
    )


def zone_device_info(entry_id: str, zone_id: int) -> DeviceInfo:
    """Device representing a single zone, linked to its unit's master device.

    `zone_id` may itself be a master zone id (10/20/30), in which case the
    unit device is returned directly.
    """
    unit = zone_id // 10
    if zone_id % 10 == 0:
        return unit_device_info(entry_id, unit)
    return DeviceInfo(
        identifiers={(DOMAIN, f"{entry_id}_{zone_id}")},
        manufacturer="Monoprice",
        model="6-Zone Amplifier",
        name=f"Zone {zone_id}",
        via_device=(DOMAIN, f"{entry_id}_{unit * 10}"),
    )
