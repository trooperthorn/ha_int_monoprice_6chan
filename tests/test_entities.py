"""Entity topology tests for late expansion discovery."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import Mock

import pytest

pytest.importorskip("homeassistant")

from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.monoprice_custom.const import CONF_ZONE_NAMES, DOMAIN
from custom_components.monoprice_custom.coordinator import MonopriceCoordinator
from custom_components.monoprice_custom.number import async_setup_entry

pytestmark = pytest.mark.usefixtures("enable_custom_integrations")


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
