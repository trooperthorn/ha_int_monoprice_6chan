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
    CONF_ZONE_NAMES,
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
    detected_units: tuple[int, ...] = (1,)


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


def _zone_ids_for_units(units: tuple[int, ...]) -> list[int]:
    """Return every zone id (unit*10+1..6) for the given detected units."""
    return [unit * 10 + zone for unit in sorted(units) for zone in range(1, 7)]


def _zone_name_form_key(zone_id: int, previous_names: dict[str, Any]) -> vol.Optional:
    """Return an optional zone-name field with its prior value suggested."""
    key = f"zone_{zone_id}"
    if str(zone_id) in previous_names:
        return vol.Optional(
            key, description={"suggested_value": previous_names[str(zone_id)]}
        )
    return vol.Optional(key)


def _zone_names_schema(
    zone_ids: list[int], previous_names: dict[str, Any] | None = None
) -> vol.Schema:
    """Build one optional room-name field per detected zone."""
    previous = previous_names or {}
    return vol.Schema(
        {_zone_name_form_key(zone_id, previous): str for zone_id in zone_ids}
    )


def _zone_names_from_config(
    data: dict[str, Any], zone_ids: list[int]
) -> dict[str, str]:
    """Convert the submitted per-zone fields into the stored name mapping."""
    return {
        str(zone_id): name.strip()
        for zone_id in zone_ids
        if (name := data.get(f"zone_{zone_id}")) is not None and name.strip()
    }


def _interface_schema(suggested_port: str | None = None) -> vol.Schema:
    """Build the single serial-port selector form used by every interface step."""
    if suggested_port:
        return vol.Schema(
            {
                vol.Required(
                    CONF_PORT, description={"suggested_value": suggested_port}
                ): SerialPortSelector()
            }
        )
    return vol.Schema({vol.Required(CONF_PORT): SerialPortSelector()})


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
    coordinator = getattr(entry.runtime_data, "coordinator", None)
    detected_units = tuple(sorted(coordinator.active_units)) if coordinator else (1,)
    return ValidationResult(detected_baud=detected_baud, detected_units=detected_units)


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
    return PreparedEndpoint(
        canonical_port, identity, validation.detected_baud, validation.detected_units
    )


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
        # Sources + baud, captured by the options step and carried forward
        # to the zone-names step, which is the one that actually creates or
        # updates the entry.
        self._pending_options: dict[str, Any] | None = None

    @override
    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Select an interface without opening or writing to any device."""
        if user_input is not None:
            self._submitted_port = user_input[CONF_PORT]
            return await self.async_step_verify()

        return self.async_show_form(step_id="user", data_schema=_interface_schema())

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
            data_schema=_interface_schema(self._reconfigure_entry.data[CONF_PORT]),
        )

    async def async_step_interface(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Re-prompt for a serial port after a failed verification attempt."""
        if user_input is not None:
            self._submitted_port = user_input[CONF_PORT]
            return await self.async_step_verify()

        return self.async_show_form(
            step_id="interface",
            data_schema=_interface_schema(self._submitted_port),
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

        if errors:
            return self.async_show_form(
                step_id="interface",
                data_schema=_interface_schema(self._submitted_port),
                errors=errors,
            )

        return self.async_show_form(
            step_id="verify",
            data_schema=vol.Schema({}),
            description_placeholders={"port": self._submitted_port},
        )

    async def async_step_options(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Configure source names and target baud, then move to zone names."""
        if self._prepared is None:
            return self.async_abort(reason="unknown")

        if user_input is not None:
            form_data = dict(user_input)
            target_baud = int(form_data.pop(CONF_BAUD_RATE))
            self._pending_options = {
                CONF_SOURCES: _sources_from_config(form_data),
                CONF_BAUD_RATE: target_baud,
            }
            return await self.async_step_zone_names()

        return self.async_show_form(
            step_id="options",
            data_schema=_options_schema(target_baud=self._prepared.detected_baud),
        )

    async def async_step_zone_names(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Name each detected zone's media player, then create the entry.

        Only Home Assistant stores this name - the amplifier itself has no
        zone-label command (see CONF_ZONE_NAMES in const.py), so an empty
        field just leaves that zone's default "Zone N" name in place.
        """
        if self._prepared is None or self._pending_options is None:
            return self.async_abort(reason="unknown")

        zone_ids = _zone_ids_for_units(self._prepared.detected_units)

        if user_input is not None:
            zone_names = _zone_names_from_config(user_input, zone_ids)
            return self.async_create_entry(
                title=self._prepared.port,
                data={
                    CONF_PORT: self._prepared.port,
                    CONF_DEVICE_IDENTITY: self._prepared.identity.key,
                    CONF_IDENTITY_KIND: self._prepared.identity.kind,
                    CONF_LAST_KNOWN_BAUD: self._prepared.detected_baud,
                },
                options={**self._pending_options, CONF_ZONE_NAMES: zone_names},
            )

        return self.async_show_form(
            step_id="zone_names",
            data_schema=_zone_names_schema(zone_ids),
        )

    async def async_step_reconfigure_options(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Update source names and target baud, then move to zone names."""
        if self._prepared is None or self._reconfigure_entry is None:
            return self.async_abort(reason="unknown")

        if user_input is not None:
            form_data = dict(user_input)
            target_baud = int(form_data.pop(CONF_BAUD_RATE))
            self._pending_options = {
                **self._reconfigure_entry.options,
                CONF_SOURCES: _sources_from_config(form_data),
                CONF_BAUD_RATE: target_baud,
            }
            return await self.async_step_reconfigure_zone_names()

        sources = self._reconfigure_entry.options.get(CONF_SOURCES, {})
        target_baud = self._reconfigure_entry.options.get(
            CONF_BAUD_RATE, self._prepared.detected_baud
        )
        return self.async_show_form(
            step_id="reconfigure_options",
            data_schema=_options_schema(sources, target_baud),
        )

    async def async_step_reconfigure_zone_names(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Rename each detected zone's media player, keeping other options."""
        if (
            self._prepared is None
            or self._reconfigure_entry is None
            or self._pending_options is None
        ):
            return self.async_abort(reason="unknown")

        zone_ids = _zone_ids_for_units(self._prepared.detected_units)
        previous_names = self._reconfigure_entry.options.get(CONF_ZONE_NAMES, {})

        if user_input is not None:
            zone_names = _zone_names_from_config(user_input, zone_ids)
            return self.async_update_and_abort(
                self._reconfigure_entry,
                data_updates={
                    CONF_PORT: self._prepared.port,
                    CONF_DEVICE_IDENTITY: self._prepared.identity.key,
                    CONF_IDENTITY_KIND: self._prepared.identity.kind,
                    CONF_LAST_KNOWN_BAUD: self._prepared.detected_baud,
                },
                options={**self._pending_options, CONF_ZONE_NAMES: zone_names},
            )

        return self.async_show_form(
            step_id="reconfigure_zone_names",
            data_schema=_zone_names_schema(zone_ids, previous_names),
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        """Return the options flow handler."""
        return MonopriceOptionsFlowHandler()


class MonopriceOptionsFlowHandler(config_entries.OptionsFlow):
    """Handle source-name, target-baud, and zone-name options.

    Reached from the integration's "Configure" gear icon, with no serial
    port involved - the entry is already set up and running, so the zone
    list comes from the live coordinator's `active_units` rather than a
    fresh probe. This is the quickest way to rename a zone's media player
    without touching Reconfigure at all.
    """

    def __init__(self) -> None:
        """Initialize transient state for the two-step options flow."""
        self._pending_options: dict[str, Any] | None = None

    @override
    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Configure source names and target baud, then move to zone names."""
        if user_input is not None:
            form_data = dict(user_input)
            target_baud = int(form_data.pop(CONF_BAUD_RATE))
            self._pending_options = {
                **self.config_entry.options,
                CONF_SOURCES: _sources_from_config(form_data),
                CONF_BAUD_RATE: target_baud,
            }
            return await self.async_step_zone_names()

        sources = self.config_entry.options.get(
            CONF_SOURCES, self.config_entry.data.get(CONF_SOURCES, {})
        )
        target_baud = self.config_entry.options.get(CONF_BAUD_RATE, POWER_ON_BAUD_RATE)
        return self.async_show_form(
            step_id="init",
            data_schema=_options_schema(sources, target_baud),
        )

    async def async_step_zone_names(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Rename each currently active zone's media player."""
        if self._pending_options is None:
            return self.async_abort(reason="unknown")

        runtime_data = getattr(self.config_entry, "runtime_data", None)
        coordinator = getattr(runtime_data, "coordinator", None)
        active_units = tuple(sorted(coordinator.active_units)) if coordinator else (1,)
        zone_ids = _zone_ids_for_units(active_units)
        previous_names = self.config_entry.options.get(CONF_ZONE_NAMES, {})

        if user_input is not None:
            zone_names = _zone_names_from_config(user_input, zone_ids)
            return self.async_create_entry(
                title="",
                data={**self._pending_options, CONF_ZONE_NAMES: zone_names},
            )

        return self.async_show_form(
            step_id="zone_names",
            data_schema=_zone_names_schema(zone_ids, previous_names),
        )
