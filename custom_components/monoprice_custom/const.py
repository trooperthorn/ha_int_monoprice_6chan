"""Constants for the Monoprice 6-Zone Amplifier Media Player component."""
from homeassistant.const import Platform

DOMAIN = "monoprice"
CONF_PORT = "port"

# Platinum Platform list
PLATFORMS = [
    Platform.MEDIA_PLAYER,
    Platform.SWITCH,
    Platform.SENSOR,
    Platform.NUMBER,
    Platform.TEXT,
    Platform.REMOTE,
]
DOMAIN = "monoprice"

# Configuration UI and Source Keys
CONF_SOURCES = "sources"
CONF_SOURCE_1 = "source_1"
CONF_SOURCE_2 = "source_2"
CONF_SOURCE_3 = "source_3"
CONF_SOURCE_4 = "source_4"
CONF_SOURCE_5 = "source_5"
CONF_SOURCE_6 = "source_6"

# Service Attributes
ATTR_BALANCE = "balance"
ATTR_BASS = "bass"
ATTR_TREBLE = "treble"

# Compatibility strings for media_player.py imports
CONF_NAME = "name"
MONOPRICE_OBJECT = "monoprice"
UNDO_UPDATE_LISTENER = "undo_update_listener"

# Integration lifecycle tracking
FIRST_RUN = "first_run"
CONF_NOT_FIRST_RUN = "not_first_run"

SERVICE_SNAPSHOT = "snapshot"
SERVICE_RESTORE = "restore"
SERVICE_SET_BALANCE = "set_balance"
SERVICE_SET_BASS = "set_bass"
SERVICE_SET_TREBLE = "set_treble"


ATTR_BALANCE = "level"
ATTR_BASS = "level"
ATTR_TREBLE = "level"
