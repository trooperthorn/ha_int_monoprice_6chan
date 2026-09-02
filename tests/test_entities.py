"""Entity topology tests for late expansion discovery."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import Mock

import pytest

pytest.importorskip("homeassistant")

from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.monoprice_custom.const import DOMAIN
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

    await async_setup_entry(hass, entry, add_entities)

    assert len(add_entities.call_args_list) == 1
    assert len(add_entities.call_args_list[0].args[0]) == 18

    coordinator.active_units = [1, 2]
    coordinator.async_set_updated_data({})
    assert len(add_entities.call_args_list) == 2
    assert len(add_entities.call_args_list[1].args[0]) == 18

    coordinator.async_set_updated_data({})
    assert len(add_entities.call_args_list) == 2
