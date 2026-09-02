"""Config flow for the Monoprice 6-Zone Amplifier integration."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Any, override

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.components import usb
from homeassistant.components.usb import USBDevice
from homeassistant.config_entries import ConfigEntry, ConfigFlowResult, OptionsFlow
from homeassistant.const import CONF_PORT
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.selector import SerialPortSelector

from .const import (
    CONF_BAUD_RATE,
    CONF_DEVICE_IDENTITY,
    CONF_IDENTITY_KIND,
    CONF_LAST_KNOWN_BAUD,
    CONF_SOURCE_1,
    CONF_SOURCE_2,
    CONF_SOURCE_3,
    CONF_SOURCE_4,
    CONF_SOURCE_5,
    CONF_SOURCE_6,
    CONF_SOURCES,
    DOMAIN,
)
from .serial import (
    POWER_ON_BAUD_RATE,
    SUPPORTED_BAUD_RATES,
    CannotOpenPort,
    EndpointIdentity,
    NotMonopriceDevice,
    ValidationResult,
    canonicalize_endpoint,
    endpoint_identity,
    validate_monoprice_endpoint,
)

_LOGGER = logging.getLogger(__name__)

SOURCES = (
    CONF_SOURCE_1,
    CONF_SOURCE_2,
    CONF_SOURCE_3,
    CONF_SOURCE_4,
    CONF_SOURCE_5,
    CONF_SOURCE_6,
)


@dataclass(frozen=True, slots=True)
class PreparedEndpoint:
    """A verified endpoint and the identity used by the config entry."""

    port: str
    identity: EndpointIdentity
    detected_baud: int


@callback
def _sources_from_config(data: dict[str, Any]) -> dict[str, str]:
    """Convert the six optional form fields into the stored source mapping."""
    return {
        str(index): name.strip()
        for index, source in enumerate(SOURCES, start=1)
        if (name := data.get(source)) is not None and name.strip()
    }


def _source_form_key(
    source: str, index: int, previous_sources: dict[str, Any]
) -> vol.Optional:
    """Return an optional source field with its prior value suggested."""
    if str(index) in previous_sources:
        return vol.Optional(
            source,
            description={"suggested_value": previous_sources[str(index)]},
        )
    return vol.Optional(source)


def _options_schema(
    sources: dict[str, Any] | None = None,
    target_baud: int = POWER_ON_BAUD_RATE,
) -> vol.Schema:
    """Build the shared sources and target-baud form schema."""
    previous_sources = sources or {}
    fields: dict[Any, Any] = {
        _source_form_key(source, index, previous_sources): str
        for index, source in enumerate(SOURCES, start=1)
    }
    fields[vol.Required(CONF_BAUD_RATE, default=target_baud)] = vol.In(
        SUPPORTED_BAUD_RATES
    )
    return vol.Schema(fields)


def _same_local_device(first: str, second: str) -> bool:
    """Compare local device aliases without rewriting serial URLs."""
    if first == second:
        return True
    if "://" in first or "://" in second:
        return False
    return os.path.realpath(first) == os.path.realpath(second)


async def _async_adapter_identity(
    hass: HomeAssistant, canonical_port: str
) -> EndpointIdentity:
    """Prefer immutable USB adapter metadata for the verified endpoint."""
    try:
        devices = await usb.async_scan_serial_ports(hass)
    except Exception:  # pragma: no cover - platform USB enumeration is best effort
        _LOGGER.debug("Unable to enumerate USB metadata", exc_info=True)
        return endpoint_identity(canonical_port)

    for device in devices:
        if (
            isinstance(device, USBDevice)
            and device.device
            and _same_local_device(device.device, canonical_port)
        ):
            return endpoint_identity(
                canonical_port,
                vid=device.vid,
                pid=device.pid,
                serial_number=device.serial_number,
                interface_num=device.interface_num,
            )
    return endpoint_identity(canonical_port)


async def _async_live_validation(entry: ConfigEntry) -> ValidationResult | None:
    """Validate an unchanged endpoint through its already-owned live client."""
    runtime_data = getattr(entry, "runtime_data", None)
    coordinator = getattr(runtime_data, "coordinator", None)
    gateway = getattr(coordinator, "gateway", None)
    if gateway is None:
        return None

    status = await gateway.async_zone_status(11)
    if status is None or status.zone != 11:
        raise NotMonopriceDevice(entry.data[CONF_PORT])
    detected_baud = gateway.current_baud_rate
    return ValidationResult(detected_baud=detected_baud)


async def async_prepare_endpoint(
    hass: HomeAssistant,
    submitted_port: str,
    reconfigure_entry: ConfigEntry | None = None,
) -> PreparedEndpoint:
    """Canonicalize, verify, and identify exactly one submitted endpoint."""
    canonical_port = canonicalize_endpoint(submitted_port)
    validation: ValidationResult | None = None

    if reconfigure_entry is not None and _same_local_device(
        canonical_port, reconfigure_entry.data[CONF_PORT]
    ):
        validation = await _async_live_validation(reconfigure_entry)

    if validation is None:
        validation = await hass.async_add_executor_job(
            validate_monoprice_endpoint, canonical_port
        )

    if (
        reconfigure_entry is not None
        and reconfigure_entry.data.get(CONF_IDENTITY_KIND) == "canonical_endpoint"
    ):
        identity = endpoint_identity(canonical_port)
    else:
        identity = await _async_adapter_identity(hass, canonical_port)
    return PreparedEndpoint(canonical_port, identity, validation.detected_baud)


class MonopriceConfigFlow(  # type: ignore[call-arg]
    config_entries.ConfigFlow, domain=DOMAIN
):
    """Handle the Monoprice configuration and reconfiguration flows."""

    VERSION = 2

    def __init__(self) -> None:
        """Initialize transient flow state."""
        self._submitted_port: str | None = None
        self._prepared: PreparedEndpoint | None = None
        self._reconfigure_entry: ConfigEntry | None = None

    @override
    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Select an interface without opening or writing to any device."""
        if user_input is not None:
            self._submitted_port = user_input[CONF_PORT]
            return await self.async_step_verify()

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({vol.Required(CONF_PORT): SerialPortSelector()}),
        )

    @override
    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Select a replacement interface while preserving entry ownership."""
        self._reconfigure_entry = self._get_reconfigure_entry()
        if user_input is not None:
            self._submitted_port = user_input[CONF_PORT]
            return await self.async_step_verify()

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_PORT,
                        default=self._reconfigure_entry.data[CONF_PORT],
                    ): SerialPortSelector()
                }
            ),
        )

    async def async_step_verify(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Explicitly confirm and verify only the submitted interface."""
        if self._submitted_port is None:
            return self.async_abort(reason="unknown")

        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                self._prepared = await async_prepare_endpoint(
                    self.hass,
                    self._submitted_port,
                    self._reconfigure_entry,
                )
            except CannotOpenPort:
                errors["base"] = "cannot_connect"
            except NotMonopriceDevice:
                errors["base"] = "not_monoprice"
            except Exception:  # pragma: no cover - HA displays the safe fallback
                _LOGGER.exception("Unexpected exception verifying Monoprice endpoint")
                errors["base"] = "unknown"
            else:
                if self._reconfigure_entry is None:
                    await self.async_set_unique_id(self._prepared.identity.key)
                    self._abort_if_unique_id_configured()
                    return await self.async_step_options()

                if (
                    self._reconfigure_entry.unique_id is not None
                    and self._reconfigure_entry.unique_id != self._prepared.identity.key
                ):
                    errors["base"] = "wrong_device"
                else:
                    return await self.async_step_reconfigure_options()

        return self.async_show_form(
            step_id="verify",
            data_schema=vol.Schema({}),
            errors=errors,
            description_placeholders={"port": self._submitted_port},
        )

    async def async_step_options(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Configure source names and target baud before entry creation."""
        if self._prepared is None:
            return self.async_abort(reason="unknown")

        if user_input is not None:
            form_data = dict(user_input)
            target_baud = int(form_data.pop(CONF_BAUD_RATE))
            return self.async_create_entry(
                title=self._prepared.port,
                data={
                    CONF_PORT: self._prepared.port,
                    CONF_DEVICE_IDENTITY: self._prepared.identity.key,
                    CONF_IDENTITY_KIND: self._prepared.identity.kind,
                    CONF_LAST_KNOWN_BAUD: self._prepared.detected_baud,
                },
                options={
                    CONF_SOURCES: _sources_from_config(form_data),
                    CONF_BAUD_RATE: target_baud,
                },
            )

        return self.async_show_form(
            step_id="options",
            data_schema=_options_schema(target_baud=self._prepared.detected_baud),
        )

    async def async_step_reconfigure_options(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Update a verified endpoint without discarding unrelated state."""
        if self._prepared is None or self._reconfigure_entry is None:
            return self.async_abort(reason="unknown")

        if user_input is not None:
            form_data = dict(user_input)
            target_baud = int(form_data.pop(CONF_BAUD_RATE))
            options = {
                **self._reconfigure_entry.options,
                CONF_SOURCES: _sources_from_config(form_data),
                CONF_BAUD_RATE: target_baud,
            }
            return self.async_update_and_abort(
                self._reconfigure_entry,
                data_updates={
                    CONF_PORT: self._prepared.port,
                    CONF_DEVICE_IDENTITY: self._prepared.identity.key,
                    CONF_IDENTITY_KIND: self._prepared.identity.kind,
                    CONF_LAST_KNOWN_BAUD: self._prepared.detected_baud,
                },
                options=options,
            )

        sources = self._reconfigure_entry.options.get(CONF_SOURCES, {})
        target_baud = self._reconfigure_entry.options.get(
            CONF_BAUD_RATE, self._prepared.detected_baud
        )
        return self.async_show_form(
            step_id="reconfigure_options",
            data_schema=_options_schema(sources, target_baud),
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        """Return the options flow handler."""
        return MonopriceOptionsFlowHandler()


class MonopriceOptionsFlowHandler(config_entries.OptionsFlow):
    """Handle source-name and target-baud options."""

    @override
    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manage options while preserving unrelated option keys."""
        if user_input is not None:
            form_data = dict(user_input)
            target_baud = int(form_data.pop(CONF_BAUD_RATE))
            return self.async_create_entry(
                title="",
                data={
                    **self.config_entry.options,
                    CONF_SOURCES: _sources_from_config(form_data),
                    CONF_BAUD_RATE: target_baud,
                },
            )

        sources = self.config_entry.options.get(
            CONF_SOURCES, self.config_entry.data.get(CONF_SOURCES, {})
        )
        target_baud = self.config_entry.options.get(CONF_BAUD_RATE, POWER_ON_BAUD_RATE)
        return self.async_show_form(
            step_id="init",
            data_schema=_options_schema(sources, target_baud),
        )
