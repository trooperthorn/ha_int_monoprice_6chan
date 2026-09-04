"""Shared device-registry helpers for the Monoprice integration.

See docs/design.md for why devices are modeled as controller -> unit -> zone
via `via_device_id` instead of each zone being an unrelated flat device.
"""
from __future__ import annotations

from collections.abc import Iterable

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import device_registry as dr
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


@callback
def async_ensure_unit_devices(
    hass: HomeAssistant, entry_id: str, units: Iterable[int]
) -> None:
    """Register the controller and the given units' devices if not present.

    `via_device_id` must name an already-registered device, unlike the
    retired `via_device` identifier shim, so the parent devices are created
    here before any platform builds a zone's DeviceInfo.
    """
    device_registry = dr.async_get(hass)
    controller = device_registry.async_get_or_create(
        config_entry_id=entry_id, **controller_device_info(entry_id)
    )
    for unit in units:
        device_registry.async_get_or_create(
            config_entry_id=entry_id,
            identifiers={(DOMAIN, f"{entry_id}_{unit * 10}")},
            manufacturer="Monoprice",
            model="6-Zone Amplifier",
            name=f"Unit {unit} Master",
            via_device_id=controller.id,
        )


def unit_device_info(hass: HomeAssistant, entry_id: str, unit: int) -> DeviceInfo:
    """Device representing one main unit (10/20/30), linked to the controller."""
    return DeviceInfo(
        identifiers={(DOMAIN, f"{entry_id}_{unit * 10}")},
        manufacturer="Monoprice",
        model="6-Zone Amplifier",
        name=f"Unit {unit} Master",
        via_device_id=dr.async_get_device_id_by_identifier(
            hass, (DOMAIN, entry_id), config_entry_id=entry_id
        ),
    )


def zone_device_info(hass: HomeAssistant, entry_id: str, zone_id: int) -> DeviceInfo:
    """Device representing a single zone, linked to its unit's master device.

    `zone_id` may itself be a master zone id (10/20/30), in which case the
    unit device is returned directly.
    """
    unit = zone_id // 10
    if zone_id % 10 == 0:
        return unit_device_info(hass, entry_id, unit)
    return DeviceInfo(
        identifiers={(DOMAIN, f"{entry_id}_{zone_id}")},
        manufacturer="Monoprice",
        model="6-Zone Amplifier",
        name=f"Zone {zone_id}",
        via_device_id=dr.async_get_device_id_by_identifier(
            hass, (DOMAIN, f"{entry_id}_{unit * 10}"), config_entry_id=entry_id
        ),
    )
