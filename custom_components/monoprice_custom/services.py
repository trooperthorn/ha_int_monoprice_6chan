"""Entity services for the Monoprice integration."""
from __future__ import annotations

import voluptuous as vol
from homeassistant.components.media_player import DOMAIN as MEDIA_PLAYER_DOMAIN
from homeassistant.components.remote import DOMAIN as REMOTE_DOMAIN
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import service

from .const import (
    ATTR_BALANCE,
    ATTR_BASS,
    ATTR_BAUD_RATE,
    ATTR_TREBLE,
    SERVICE_RESTORE,
    SERVICE_SET_BALANCE,
    SERVICE_SET_BASS,
    SERVICE_SET_BAUD_RATE,
    SERVICE_SET_TREBLE,
    SERVICE_SNAPSHOT,
)
from .serial import SUPPORTED_BAUD_RATES

SET_BALANCE_SCHEMA = {
    vol.Required(ATTR_BALANCE): vol.All(cv.positive_int, vol.Range(min=0, max=20))
}
SET_BASS_SCHEMA = {
    vol.Required(ATTR_BASS): vol.All(cv.positive_int, vol.Range(min=0, max=14))
}
SET_TREBLE_SCHEMA = {
    vol.Required(ATTR_TREBLE): vol.All(cv.positive_int, vol.Range(min=0, max=14))
}


@callback
def async_setup_services(hass: HomeAssistant) -> None:
    """Set up entity services."""
    service.async_register_platform_entity_service(
        hass,
        MEDIA_PLAYER_DOMAIN,
        SERVICE_SNAPSHOT,
        entity_domain=MEDIA_PLAYER_DOMAIN,
        schema=None,
        func="async_snapshot",
    )
    service.async_register_platform_entity_service(
        hass,
        MEDIA_PLAYER_DOMAIN,
        SERVICE_RESTORE,
        entity_domain=MEDIA_PLAYER_DOMAIN,
        schema=None,
        func="async_restore",
    )
    service.async_register_platform_entity_service(
        hass,
        MEDIA_PLAYER_DOMAIN,
        SERVICE_SET_BALANCE,
        entity_domain=MEDIA_PLAYER_DOMAIN,
        schema=SET_BALANCE_SCHEMA,
        func="async_set_balance",
    )
    service.async_register_platform_entity_service(
        hass,
        MEDIA_PLAYER_DOMAIN,
        SERVICE_SET_BASS,
        entity_domain=MEDIA_PLAYER_DOMAIN,
        schema=SET_BASS_SCHEMA,
        func="async_set_bass",
    )
    service.async_register_platform_entity_service(
        hass,
        MEDIA_PLAYER_DOMAIN,
        SERVICE_SET_TREBLE,
        entity_domain=MEDIA_PLAYER_DOMAIN,
        schema=SET_TREBLE_SCHEMA,
        func="async_set_treble",
    )
    service.async_register_platform_entity_service(
        hass,
        REMOTE_DOMAIN,
        SERVICE_SET_BAUD_RATE,
        entity_domain=REMOTE_DOMAIN,
        schema={vol.Required(ATTR_BAUD_RATE): vol.In(SUPPORTED_BAUD_RATES)},
        func="async_set_baud_rate",
    )
