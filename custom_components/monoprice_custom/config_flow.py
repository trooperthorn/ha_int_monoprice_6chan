"""Config flow for Monoprice 6-Zone Amplifier integration."""
from __future__ import annotations

import logging
import os
from typing import Any

from pymonoprice import get_monoprice
import serial
from serial import SerialException
import serial.tools.list_ports
import voluptuous as vol

from homeassistant import config_entries, core, exceptions
from homeassistant.const import CONF_PORT
from homeassistant.helpers import selector

from .const import (
    CONF_SOURCE_1,
    CONF_SOURCE_2,
    CONF_SOURCE_3,
    CONF_SOURCE_4,
    CONF_SOURCE_5,
    CONF_SOURCE_6,
    CONF_SOURCES,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)

SOURCES = [
    CONF_SOURCE_1,
    CONF_SOURCE_2,
    CONF_SOURCE_3,
    CONF_SOURCE_4,
    CONF_SOURCE_5,
    CONF_SOURCE_6,
]

OPTIONS_FOR_DATA = {vol.Optional(source): str for source in SOURCES}


def _resolve_path(path: str) -> str:
    """Resolve symlinks like /dev/serial/by-id/... to /dev/ttyUSBx."""
    try:
        return os.path.realpath(path)
    except Exception:
        return path


def _find_dev_paths(obj: Any) -> set[str]:
    """Recursively search a data structure for any device paths starting with /dev/."""
    found = set()
    if isinstance(obj, dict):
        for val in obj.values():
            found.update(_find_dev_paths(val))
    elif isinstance(obj, (list, tuple, set)):
        for item in obj:
            found.update(_find_dev_paths(item))
    elif isinstance(obj, str):
        if obj.startswith("/dev/"):
            found.add(obj)
            found.add(_resolve_path(obj))
    return found


@core.callback
def _sources_from_config(data: dict[str, Any]) -> dict[str, str]:
    sources_config = {
        str(idx + 1): data.get(source) for idx, source in enumerate(SOURCES)
    }

    return {
        index: name.strip()
        for index, name in sources_config.items()
        if (name is not None and name.strip() != "")
    }


async def validate_input(hass: core.HomeAssistant, data: dict[str, Any]) -> dict[str, Any]:
    """Validate the user input allows us to connect."""
    try:
        await hass.async_add_executor_job(get_monoprice, data[CONF_PORT])
    except SerialException as err:
        _LOGGER.error("Error connecting to Monoprice controller %s", data[CONF_PORT])
        raise CannotConnect from err

    sources = _sources_from_config(data)
    return {CONF_PORT: data[CONF_PORT], CONF_SOURCES: sources}


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Monoprice 6-Zone Amplifier."""

    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None):
        """Handle the initial step."""
        errors = {}

        if user_input is not None:
            try:
                info = await validate_input(self.hass, user_input)
                return self.async_create_entry(title=user_input[CONF_PORT], data=info)
            except CannotConnect:
                errors["base"] = "cannot_connect"
            except Exception:  
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"

        # 1. Map all active HA integration entries to device paths they consume
        ha_configured_ports: dict[str, str] = {}
        for entry in self.hass.config_entries.async_entries():
            dev_paths = _find_dev_paths(entry.data) | _find_dev_paths(entry.options)
            for path in dev_paths:
                # Store domain (e.g. 'zwave_js', 'zha', 'elkm1')
                ha_configured_ports[path] = entry.domain

        # 2. Smart Hardware Probe
        def _get_port_status(port):
            device_path = port.device
            resolved_path = _resolve_path(device_path)
            
            status_label = "(Available)"
            amp = None

            # If HA already claimed this port for another integration, skip probing completely
            if device_path in ha_configured_ports or resolved_path in ha_configured_ports:
                using_domain = ha_configured_ports.get(device_path) or ha_configured_ports.get(resolved_path)
                status_label = f"(In Use by {using_domain})"
            else:
                # Safe to probe: test if the port responds to Monoprice commands
                try:
                    amp = get_monoprice(device_path)
                    
                    # Temporarily drop timeout to 0.5s so non-matching ports don't delay the UI
                    if hasattr(amp, "_port"):
                        amp._port.timeout = 0.5
                        amp._port.write(b"\r\n")
                    
                    # Query Zone 11 to see if amplifier responds
                    zone_status = amp.zone_status(11)
                    if zone_status:
                        status_label = "(Monoprice Amp Detected) 🎯"
                        
                except Exception as err:
                    if "timed out" in str(err) or "received bytes" in str(err):
                        status_label = "(Available)"
                    else:
                        # PermissionError, OS lock, or busy
                        status_label = "(In Use by OS)"
                finally:
                    # Failsafe: Always close the serial port immediately
                    try:
                        if amp and hasattr(amp, "_port") and amp._port.is_open:
                            amp._port.close()
                    except Exception:
                        pass

            label = f"{device_path} - {port.description}" if port.description and port.description != "n/a" else device_path
            
            return {
                "value": device_path,
                "label": f"{label} {status_label}",
            }

        # 3. Offload scanning and probing to the executor
        ports = await self.hass.async_add_executor_job(serial.tools.list_ports.comports)
        port_options = await self.hass.async_add_executor_job(
            lambda: [_get_port_status(p) for p in ports]
        )

        # Build schema using the dynamic dropdown
        data_schema = vol.Schema(
            {
                vol.Required(CONF_PORT): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=port_options,
                        mode=selector.SelectSelectorMode.DROPDOWN,
                        custom_value=True,
                    )
                ),
                **OPTIONS_FOR_DATA,
            }
        )

        return self.async_show_form(
            step_id="user", data_schema=data_schema, errors=errors
        )

    @staticmethod
    @core.callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> MonopriceOptionsFlowHandler:
        """Define the config flow to handle options."""
        return MonopriceOptionsFlowHandler()


@core.callback
def _key_for_source(index: int, source: str, previous_sources: dict[str, Any]) -> vol.Optional:
    if str(index) in previous_sources:
        key = vol.Optional(
            source, description={"suggested_value": previous_sources[str(index)]}
        )
    else:
        key = vol.Optional(source)
    return key


class MonopriceOptionsFlowHandler(config_entries.OptionsFlow):
    """Handle a Monoprice options flow."""

    @core.callback
    def _previous_sources(self) -> dict[str, Any]:
        if CONF_SOURCES in self.config_entry.options:
            previous = self.config_entry.options[CONF_SOURCES]
        else:
            previous = self.config_entry.data[CONF_SOURCES]
        return previous

    async def async_step_init(self, user_input: dict[str, Any] | None = None):
        """Manage the options."""
        if user_input is not None:
            return self.async_create_entry(
                title="", data={CONF_SOURCES: _sources_from_config(user_input)}
            )

        previous_sources = self._previous_sources()
        options = {
            _key_for_source(idx + 1, source, previous_sources): str
            for idx, source in enumerate(SOURCES)
        }

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(options),
        )


class CannotConnect(exceptions.HomeAssistantError):
    """Error to indicate we cannot connect."""
