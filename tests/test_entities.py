"""Entity topology tests for late expansion discovery."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

pytest.importorskip("homeassistant")

from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.monoprice_custom.const import CONF_ZONE_NAMES, DOMAIN
from custom_components.monoprice_custom.coordinator import MonopriceCoordinator
from custom_components.monoprice_custom.number import (
    EQ_WIRE_OFFSET,
    MonopriceZoneNumber,
    async_setup_entry,
)

pytestmark = pytest.mark.usefixtures("enable_custom_integrations")


@pytest.mark.parametrize(
    ("control", "display", "wire"),
    (
        # Round-tripped on a 10761: these exact pairs were written and read
        # back unchanged, and match the openHAB binding's toneOffset=7 and
        # balOffset=10 for this family. See docs/protocol.md.
        ("Bass", -7, 0),
        ("Bass", 0, 7),
        ("Bass", 7, 14),
        ("Treble", -7, 0),
        ("Treble", 7, 14),
        ("Balance", -10, 0),
        ("Balance", 0, 10),
        ("Balance", 10, 20),
    ),
)
async def test_eq_display_values_match_the_wire(
    hass, control: str, display: int, wire: int
) -> None:
    """The offsets the user sees and the ones sent to the amplifier agree."""
    entry = MockConfigEntry(domain=DOMAIN, data={}, options={})
    entry.add_to_hass(hass)
    gateway = SimpleNamespace(async_execute=AsyncMock())
    coordinator = MonopriceCoordinator(hass, gateway, entry)
    coordinator.active_units = [1]

    number = MonopriceZoneNumber(hass, coordinator, entry.entry_id, 11, control)

    # Reading: a wire value is shown as the signed display value.
    field = {"Bass": "bass", "Treble": "treble", "Balance": "balance"}[control]
    coordinator.data = {11: SimpleNamespace(**{field: wire})}
    assert number.native_value == display

    # Writing: the display value is translated back before it is sent.
    coordinator.async_refresh_zone = AsyncMock()
    await number.async_set_native_value(display)
    method = {"Bass": "set_bass", "Treble": "set_treble", "Balance": "set_balance"}[
        control
    ]
    gateway.async_execute.assert_awaited_once_with(method, 11, wire)


def test_eq_offset_is_half_the_wire_range() -> None:
    """A changed offset would silently misreport every tone value."""
    assert EQ_WIRE_OFFSET == 7


async def test_late_expansion_adds_entities_without_precreating_all_units(hass) -> None:
    """Only detected units are registered, and a newly found unit is added once."""
    entry = MockConfigEntry(domain=DOMAIN, data={}, options={})
    entry.add_to_hass(hass)
    coordinator = MonopriceCoordinator(hass, SimpleNamespace(), entry)
    coordinator.active_units = [1]
    entry.runtime_data = SimpleNamespace(coordinator=coordinator)
    add_entities = Mock()

    try:
        await async_setup_entry(hass, entry, add_entities)

        assert len(add_entities.call_args_list) == 1
        assert len(add_entities.call_args_list[0].args[0]) == 18

        coordinator.active_units = [1, 2]
        coordinator.async_set_updated_data({})
        assert len(add_entities.call_args_list) == 2
        assert len(add_entities.call_args_list[1].args[0]) == 18

        coordinator.async_set_updated_data({})
        assert len(add_entities.call_args_list) == 2
    finally:
        await coordinator.async_shutdown()


async def test_zone_names_option_renames_only_the_matching_zone(hass) -> None:
    """A stored zone name becomes that zone's device name; others keep the default."""
    entry = MockConfigEntry(
        domain=DOMAIN, data={}, options={CONF_ZONE_NAMES: {"11": "Kitchen"}}
    )
    entry.add_to_hass(hass)
    coordinator = MonopriceCoordinator(hass, SimpleNamespace(), entry)
    coordinator.active_units = [1]
    entry.runtime_data = SimpleNamespace(coordinator=coordinator)
    add_entities = Mock()

    try:
        await async_setup_entry(hass, entry, add_entities)
        entities = {e._zone_id: e for e in add_entities.call_args_list[0].args[0]}

        assert entities[11]._attr_device_info["name"] == "Kitchen"
        assert entities[12]._attr_device_info["name"] == "Zone 12"
    finally:
        await coordinator.async_shutdown()
