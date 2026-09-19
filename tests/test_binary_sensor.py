"""The connectivity sensor must stay readable while the amplifier is not.

A CoordinatorEntity normally reports itself unavailable once the coordinator's
update fails. For a connectivity sensor that is backwards: it would go quiet at
exactly the moment it has something to say, showing "unavailable" instead of
"disconnected" and leaving nothing for an automation to trigger on.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

pytest.importorskip("homeassistant.config_entries")

from homeassistant.components.binary_sensor import BinarySensorDeviceClass
from homeassistant.const import EntityCategory
from homeassistant.helpers.update_coordinator import UpdateFailed
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.monoprice_custom.binary_sensor import MonopriceConnectionSensor
from custom_components.monoprice_custom.const import (
    CONF_BAUD_RATE,
    CONF_LAST_KNOWN_BAUD,
    DOMAIN,
)
from custom_components.monoprice_custom.coordinator import MonopriceCoordinator

pytestmark = pytest.mark.usefixtures("enable_custom_integrations")


class FakeGateway:
    """Gateway fake whose reachability can be switched at will."""

    def __init__(self) -> None:
        self.last_known_baud = 9600
        self.last_detected_baud = 9600
        self.current_baud_rate = 9600
        self.reconnect_count = 0
        self.fail_with: Exception | None = None

    async def async_ensure_link(self, target: int) -> int:
        return target

    async def async_zone_status(self, zone: int):
        if self.fail_with is not None:
            raise self.fail_with
        return SimpleNamespace(zone=zone)

    async def async_wake(self) -> None:
        return


def _build(hass):
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_LAST_KNOWN_BAUD: 9600},
        options={CONF_BAUD_RATE: 9600},
    )
    entry.add_to_hass(hass)
    gateway = FakeGateway()
    coordinator = MonopriceCoordinator(hass, gateway, entry)
    return gateway, coordinator, MonopriceConnectionSensor(coordinator, entry.entry_id)


async def test_reports_disconnected_rather_than_unavailable(hass) -> None:
    """The entity stays available through an outage and flips to off."""
    gateway, coordinator, sensor = _build(hass)

    await coordinator._async_update_data()
    assert sensor.available is True
    assert sensor.is_on is True

    gateway.fail_with = TimeoutError("amplifier is off")
    with pytest.raises(UpdateFailed):
        await coordinator._async_update_data()
    coordinator.last_update_success = False

    assert sensor.available is True, "must not go unavailable during an outage"
    assert sensor.is_on is False


async def test_is_a_diagnostic_connectivity_entity(hass) -> None:
    """Classification matters: this belongs with diagnostics, not controls."""
    _, _, sensor = _build(hass)
    assert sensor.device_class is BinarySensorDeviceClass.CONNECTIVITY
    assert sensor.entity_category is EntityCategory.DIAGNOSTIC


async def test_attributes_carry_the_outage_history(hass) -> None:
    """The attributes are what a serial-versus-power diagnosis is read from."""
    gateway, coordinator, sensor = _build(hass)
    await coordinator._async_update_data()

    gateway.last_known_baud = 19200
    gateway.fail_with = TimeoutError("gone")
    with pytest.raises(UpdateFailed):
        await coordinator._async_update_data()

    attrs = sensor.extra_state_attributes
    assert attrs["offline_since"] is not None
    assert attrs["outage_count"] == 1
    assert attrs["retry_in_seconds"] == 5.0

    # Recovered at 9600 having been at 19200: the amplifier was power cycled.
    gateway.fail_with = None
    gateway.last_detected_baud = 9600
    await coordinator._async_update_data()

    attrs = sensor.extra_state_attributes
    assert attrs["offline_since"] is None
    assert attrs["last_offline_at"] is not None
    assert attrs["last_outage_cause"] == "power_cycle"
    assert attrs["last_outage_seconds"] is not None
