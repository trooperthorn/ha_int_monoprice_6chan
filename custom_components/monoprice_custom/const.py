"""Constants for the Monoprice 6-Zone Amplifier Media Player component."""
from homeassistant.const import Platform

DOMAIN = "monoprice"
CONF_PORT = "port"

PLATFORMS = [
    Platform.MEDIA_PLAYER,
    Platform.REMOTE,
    Platform.NUMBER,
    Platform.SWITCH,
    Platform.SENSOR,
]
DOMAIN = "monoprice"

CONF_SOURCES = "sources"

CONF_SOURCE_1 = "source_1"
CONF_SOURCE_2 = "source_2"
CONF_SOURCE_3 = "source_3"
CONF_SOURCE_4 = "source_4"
CONF_SOURCE_5 = "source_5"
CONF_SOURCE_6 = "source_6"

CONF_NOT_FIRST_RUN = "not_first_run"

SERVICE_SNAPSHOT = "snapshot"
SERVICE_RESTORE = "restore"
SERVICE_SET_BALANCE = "set_balance"
SERVICE_SET_BASS = "set_bass"
SERVICE_SET_TREBLE = "set_treble"

FIRST_RUN = "first_run"

ATTR_BALANCE = "level"
ATTR_BASS = "level"
ATTR_TREBLE = "level"
