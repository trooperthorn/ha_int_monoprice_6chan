"""Coordinator recovery and expansion rediscovery tests."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

pytest.importorskip("homeassistant")

from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.monoprice_custom.const import (
    CONF_BAUD_RATE,
    CONF_LAST_KNOWN_BAUD,
    DOMAIN,
)
from custom_components.monoprice_custom.coordinator import MonopriceCoordinator

pytestmark = pytest.mark.usefixtures("enable_custom_integrations")


class FakeGateway:
    """Gateway fake with selectable expansion-unit responses."""

    def __init__(self) -> None:
        self.last_known_baud = 9600
        self.ensure_calls: list[int] = []
        self.present_units = {1}

    async def async_ensure_link(self, target: int) -> int:
        self.ensure_calls.append(target)
        self.last_known_baud = target
        return target

    async def async_zone_status(self, zone: int):
        unit = zone // 10
        if unit not in self.present_units:
            return None
        return SimpleNamespace(zone=zone)

    async def async_wake(self) -> None:
        return


async def test_first_update_runs_bounded_recovery(hass) -> None:
    """The first poll recovers the link and negotiates the configured target."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_LAST_KNOWN_BAUD: 9600},
        options={CONF_BAUD_RATE: 38400},
    )
    entry.add_to_hass(hass)
    gateway = FakeGateway()
    coordinator = MonopriceCoordinator(hass, gateway, entry)

    data = await coordinator._async_update_data()

    assert gateway.ensure_calls == [38400]
    assert coordinator.active_units == [1]
    assert set(data) == {10, 11, 12, 13, 14, 15, 16}


async def test_expansion_unit_return_is_rediscovered(hass) -> None:
    """An expansion absent at startup can become active without a reload."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_LAST_KNOWN_BAUD: 9600},
        options={CONF_BAUD_RATE: 9600},
    )
    entry.add_to_hass(hass)
    gateway = FakeGateway()
    coordinator = MonopriceCoordinator(hass, gateway, entry)

    await coordinator._async_discover_active_units()
    assert coordinator.active_units == [1]

    gateway.present_units.add(2)
    await coordinator._async_discover_active_units()
    assert coordinator.active_units == [1, 2]
