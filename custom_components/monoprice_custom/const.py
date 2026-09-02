"""Constants for the Monoprice 6-Zone Amplifier Media Player component."""

from homeassistant.const import Platform

DOMAIN = "monoprice_custom"
CONF_PORT = "port"
CONF_DEVICE_IDENTITY = "device_identity"
CONF_IDENTITY_KIND = "identity_kind"
CONF_LAST_KNOWN_BAUD = "last_known_baud"
CONF_KNOWN_UNITS = "known_units"

PLATFORMS = [
    Platform.MEDIA_PLAYER,
    Platform.SWITCH,
    Platform.SENSOR,
    Platform.NUMBER,
    Platform.TEXT,
    Platform.REMOTE,
]

# Configuration UI and Source Keys
CONF_SOURCES = "sources"
CONF_SOURCE_1 = "source_1"
CONF_SOURCE_2 = "source_2"
CONF_SOURCE_3 = "source_3"
CONF_SOURCE_4 = "source_4"
CONF_SOURCE_5 = "source_5"
CONF_SOURCE_6 = "source_6"
CONF_BAUD_RATE = "baud_rate"

# Compatibility strings for media_player.py imports
CONF_NAME = "name"
MONOPRICE_OBJECT = "monoprice_custom"
UNDO_UPDATE_LISTENER = "undo_update_listener"

# Integration lifecycle tracking
FIRST_RUN = "first_run"
CONF_NOT_FIRST_RUN = "not_first_run"

SERVICE_SNAPSHOT = "snapshot"
SERVICE_RESTORE = "restore"
SERVICE_SET_BALANCE = "set_balance"
SERVICE_SET_BASS = "set_bass"
SERVICE_SET_TREBLE = "set_treble"
SERVICE_SET_BAUD_RATE = "set_baud_rate"

ATTR_BAUD_RATE = "baud_rate"

# Service field names - these are the raw 0-14/0-20 wire-protocol values,
# distinct from the signed dB-style ranges number.py exposes to the UI.
ATTR_BALANCE = "level"
ATTR_BASS = "level"
ATTR_TREBLE = "level"
