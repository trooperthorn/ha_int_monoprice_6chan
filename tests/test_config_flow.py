"""Home Assistant config-flow contract tests."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

pytest.importorskip("homeassistant")

from homeassistant import config_entries
from homeassistant.const import CONF_PORT
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.monoprice_custom.config_flow import PreparedEndpoint
from custom_components.monoprice_custom.const import (
    CONF_BAUD_RATE,
    CONF_DEVICE_IDENTITY,
    CONF_IDENTITY_KIND,
    CONF_LAST_KNOWN_BAUD,
    CONF_SOURCE_1,
    CONF_SOURCES,
    DOMAIN,
)
from custom_components.monoprice_custom.serial import (
    CannotOpenPort,
    EndpointIdentity,
    NotMonopriceDevice,
)

pytestmark = pytest.mark.usefixtures("enable_custom_integrations")

PORT = "/dev/serial/by-id/usb-test"
IDENTITY = EndpointIdentity("monoprice:test", "usb_serial")
PREPARED = PreparedEndpoint(PORT, IDENTITY, 9600)


async def test_rendering_and_selection_do_not_touch_serial(hass) -> None:
    """No port is opened until the explicit verify step is submitted."""
    prepare = AsyncMock(return_value=PREPARED)
    with patch(
        "custom_components.monoprice_custom.config_flow.async_prepare_endpoint",
        prepare,
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        assert result["type"] is FlowResultType.FORM
        assert result["step_id"] == "user"
        prepare.assert_not_awaited()

        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_PORT: PORT}
        )
        assert result["step_id"] == "verify"
        prepare.assert_not_awaited()

        result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
        assert result["step_id"] == "options"
        prepare.assert_awaited_once_with(hass, PORT, None)

        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_SOURCE_1: "TV", CONF_BAUD_RATE: 38400}
        )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"] == {
        CONF_PORT: PORT,
        CONF_DEVICE_IDENTITY: IDENTITY.key,
        CONF_IDENTITY_KIND: IDENTITY.kind,
        CONF_LAST_KNOWN_BAUD: 9600,
    }
    assert result["options"] == {
        CONF_SOURCES: {"1": "TV"},
        CONF_BAUD_RATE: 38400,
    }


@pytest.mark.parametrize(
    ("error", "translation_key"),
    (
        (CannotOpenPort(PORT), "cannot_connect"),
        (NotMonopriceDevice(PORT), "not_monoprice"),
    ),
)
async def test_verify_reports_busy_and_wrong_devices(
    hass, error: Exception, translation_key: str
) -> None:
    """Verification distinguishes an inaccessible endpoint from a wrong device."""
    with patch(
        "custom_components.monoprice_custom.config_flow.async_prepare_endpoint",
        AsyncMock(side_effect=error),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_PORT: PORT}
        )
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {})

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": translation_key}


async def test_duplicate_identity_is_rejected(hass) -> None:
    """Two entries cannot own the same amplifier adapter identity."""
    MockConfigEntry(
        domain=DOMAIN,
        unique_id=IDENTITY.key,
        data={CONF_PORT: PORT},
    ).add_to_hass(hass)

    with patch(
        "custom_components.monoprice_custom.config_flow.async_prepare_endpoint",
        AsyncMock(return_value=PREPARED),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_PORT: PORT}
        )
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {})

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_reconfigure_preserves_unrelated_data_and_options(hass) -> None:
    """Reconfigure updates ownership fields without replacing unrelated state."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        version=2,
        unique_id=IDENTITY.key,
        data={
            CONF_PORT: "COM4",
            CONF_DEVICE_IDENTITY: IDENTITY.key,
            CONF_IDENTITY_KIND: IDENTITY.kind,
            CONF_LAST_KNOWN_BAUD: 9600,
            "internal_marker": "keep",
        },
        options={CONF_SOURCES: {"1": "Old"}, "unrelated_option": "keep"},
    )
    entry.add_to_hass(hass)

    with patch(
        "custom_components.monoprice_custom.config_flow.async_prepare_endpoint",
        AsyncMock(return_value=PREPARED),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={
                "source": config_entries.SOURCE_RECONFIGURE,
                "entry_id": entry.entry_id,
            },
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_PORT: PORT}
        )
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
        assert result["step_id"] == "reconfigure_options"
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_SOURCE_1: "TV", CONF_BAUD_RATE: 57600}
        )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert entry.data["internal_marker"] == "keep"
    assert entry.data[CONF_PORT] == PORT
    assert entry.options["unrelated_option"] == "keep"
    assert entry.options[CONF_BAUD_RATE] == 57600


async def test_options_change_preserves_unrelated_options(hass) -> None:
    """Changing target baud does not discard other option ownership."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_PORT: PORT},
        options={
            CONF_SOURCES: {"1": "TV"},
            CONF_BAUD_RATE: 9600,
            "unrelated_option": "keep",
        },
    )
    entry.add_to_hass(hass)

    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_SOURCE_1: "TV", CONF_BAUD_RATE: 115200}
    )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"]["unrelated_option"] == "keep"
    assert result["data"][CONF_BAUD_RATE] == 115200
