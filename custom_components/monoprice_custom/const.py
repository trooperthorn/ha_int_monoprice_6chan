"""Constants for the Monoprice 6-Zone Amplifier Media Player component."""

from homeassistant.const import Platform

DOMAIN = "monoprice_custom"
CONF_PORT = "port"
CONF_DEVICE_IDENTITY = "device_identity"
CONF_IDENTITY_KIND = "identity_kind"
CONF_LAST_KNOWN_BAUD = "last_known_baud"
CONF_KNOWN_UNITS = "known_units"

PLATFORMS = [
    Platform.BINARY_SENSOR,
    Platform.MEDIA_PLAYER,
    Platform.SWITCH,
    Platform.SENSOR,
    Platform.NUMBER,
    Platform.TEXT,
    Platform.REMOTE,
]

CONF_SOURCES = "sources"
# Maps zone id (as a string key, e.g. "11") to a user-assigned room name. The
# amplifier itself has no concept of a zone label - only a source label (see
# CONF_SOURCE_1..6 and text.py's rename_source command) - so this can only
# ever live in the config entry, never on the device.
CONF_ZONE_NAMES = "zone_names"
CONF_SOURCE_1 = "source_1"
CONF_SOURCE_2 = "source_2"
CONF_SOURCE_3 = "source_3"
CONF_SOURCE_4 = "source_4"
CONF_SOURCE_5 = "source_5"
CONF_SOURCE_6 = "source_6"
CONF_BAUD_RATE = "baud_rate"

# How often to poll, in seconds. The Monoprice family sends nothing on its
# own (see docs/design.md), so polling is the only way a keypad or
# front-panel change reaches Home Assistant, and the right interval is a
# trade between responsiveness and traffic on a shared RS-232 line.
CONF_POLL_INTERVAL = "poll_interval"
MIN_POLL_INTERVAL = 5
MAX_POLL_INTERVAL = 60
DEFAULT_POLL_INTERVAL = 5

# Highest volume any zone may be set to through this integration. The wire
# maximum is 38; a lower cap protects zones whose speakers cannot take it.
CONF_MAX_VOLUME = "max_volume"
# The amplifier's own volume range; see docs/protocol.md.
MAX_VOLUME_STEPS = 38
DEFAULT_MAX_VOLUME = MAX_VOLUME_STEPS

# Volume forced on a unit when its master zone is switched on. 0 disables
# it and leaves whatever the zones were last set to, which is the failure
# mode of six zones jumping to the master's last level at once.
CONF_ALL_ON_VOLUME = "all_on_volume"
DEFAULT_ALL_ON_VOLUME = 0

# Zone ids that a master (broadcast) write must skip. Turning everything
# off is deliberately exempt, so a bathroom or an outdoor zone can be kept
# out of "all on" without also being kept out of "all off".
CONF_IGNORE_ZONES = "ignore_zones"

CONF_NAME = "name"
MONOPRICE_OBJECT = "monoprice_custom"
UNDO_UPDATE_LISTENER = "undo_update_listener"

FIRST_RUN = "first_run"
CONF_NOT_FIRST_RUN = "not_first_run"

SERVICE_SNAPSHOT = "snapshot"
SERVICE_RESTORE = "restore"
SERVICE_SET_BALANCE = "set_balance"
SERVICE_SET_BASS = "set_bass"
SERVICE_SET_TREBLE = "set_treble"
SERVICE_SET_BAUD_RATE = "set_baud_rate"

ATTR_BAUD_RATE = "baud_rate"

# Raw wire-protocol values, not the display values; see docs/protocol.md.
ATTR_BALANCE = "level"
ATTR_BASS = "level"
ATTR_TREBLE = "level"
