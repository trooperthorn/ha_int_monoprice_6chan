"""Integration setup and shutdown lifecycle tests."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import pytest

pytest.importorskip("homeassistant.exceptions")

from homeassistant.exceptions import ConfigEntryNotReady
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.monoprice_custom import async_setup_entry
from custom_components.monoprice_custom.const import (
    CONF_DEVICE_IDENTITY,
    CONF_IDENTITY_KIND,
    CONF_LAST_KNOWN_BAUD,
    DOMAIN,
)

pytestmark = pytest.mark.usefixtures("enable_custom_integrations")


async def test_failed_initial_refresh_closes_client(hass) -> None:
    """A setup failure cannot leave the selected serial interface open."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        version=2,
        unique_id="monoprice:test",
        data={
            "port": "COM7",
            CONF_DEVICE_IDENTITY: "monoprice:test",
            CONF_IDENTITY_KIND: "canonical_endpoint",
            CONF_LAST_KNOWN_BAUD: 9600,
        },
        options={},
    )
    entry.add_to_hass(hass)
    api = SimpleNamespace(current_baud_rate=9600, close=Mock())

    with (
        patch(
            "custom_components.monoprice_custom.get_monoprice_extended",
            return_value=api,
        ),
        patch(
            "custom_components.monoprice_custom.MonopriceCoordinator."
            "async_config_entry_first_refresh",
            AsyncMock(side_effect=ConfigEntryNotReady),
        ),
        pytest.raises(ConfigEntryNotReady),
    ):
        await async_setup_entry(hass, entry)

    api.close.assert_called_once_with()
