"""Extended Monoprice RS-232 client.

``pymonoprice`` only implements power/mute/volume/treble/bass/balance/source.
The Monoprice Multizone Controller RS-232 spec documents several more
commands the amplifier accepts that the upstream library never wraps: paging
(PA), do-not-disturb (DT), source/keypad renaming, and baud-rate switching.
This module subclasses ``pymonoprice.Monoprice`` to add those, reusing its
``_lock``/``_process_request`` machinery so every write - polling included -
goes through the same serialized path instead of racing raw port access.
"""
from __future__ import annotations

import logging
from threading import RLock

from pymonoprice import Monoprice, synchronized

_LOGGER = logging.getLogger(__name__)

# Baud rates the amplifier firmware accepts via the `<BAUD\r` command.
# These are fixed enumerated tokens, not a free-form value: the amp firmware
# only recognizes an exact match against one of these six strings.
SUPPORTED_BAUD_RATES = (9600, 19200, 38400, 57600, 115200, 230400)

# Default baud rate the amp always reverts to on power loss.
POWER_ON_BAUD_RATE = 9600


def _format_set_pa(zone: int, pa: bool) -> bytes:
    return "<{}PA{}\r".format(zone, "01" if pa else "00").encode()


def _format_set_dnd(zone: int, dnd: bool) -> bytes:
    return "<{}DT{}\r".format(zone, "01" if dnd else "00").encode()


def _format_rename_source(index: int, name: str) -> bytes:
    return "{}<{:8}\r".format(index, name[:8]).encode("ascii")


def _format_set_keypad_message(name: str) -> bytes:
    return "M<{:8}\r".format(name[:8]).encode("ascii")


def _format_set_baud_rate(baud: int) -> bytes:
    return "<{}\r".format(baud).encode()


def _format_zone_field_status(zone: int, field: str) -> bytes:
    return "?{}{}\r".format(zone, field).encode()


class MonopriceExtended(Monoprice):
    """Monoprice client extended with PA/DND/rename/baud commands."""

    @synchronized  # type: ignore[arg-type]  # decorator is typed against the base Monoprice class
    def set_pa(self, zone: int, pa: bool) -> None:
        """Turn the zone's paging (PA) override on or off."""
        self._process_request(_format_set_pa(zone, pa))

    @synchronized  # type: ignore[arg-type]  # decorator is typed against the base Monoprice class
    def set_dnd(self, zone: int, dnd: bool) -> None:
        """Turn the zone's do-not-disturb (DT) flag on or off."""
        self._process_request(_format_set_dnd(zone, dnd))

    @synchronized  # type: ignore[arg-type]  # decorator is typed against the base Monoprice class
    def rename_source(self, index: int, name: str) -> None:
        """Rename source `index` (1-6) on the keypad displays.

        `name` is padded/truncated to the 8 ASCII characters the hardware
        requires.
        """
        self._process_request(_format_rename_source(index, name.ljust(8)))

    @synchronized  # type: ignore[arg-type]  # decorator is typed against the base Monoprice class
    def set_keypad_message(self, name: str) -> None:
        """Set the boot welcome message shown on zone keypads."""
        self._process_request(_format_set_keypad_message(name.ljust(8)))

    @synchronized  # type: ignore[arg-type]  # decorator is typed against the base Monoprice class
    def zone_field_status(self, zone: int, field: str) -> str:
        """Query a single status field (e.g. "VO") instead of the full block.

        Cuts the amount of data read/parsed when only one value changed,
        lowering the latency between an on-amp change and its reflection
        in Home Assistant.
        """
        return self._process_request(_format_zone_field_status(zone, field))

    @synchronized  # type: ignore[arg-type]  # decorator is typed against the base Monoprice class
    def send_raw(self, command: str) -> str:
        """Send an arbitrary already-formatted command, locked against polling."""
        if not command.endswith("\r"):
            command += "\r"
        return self._process_request(command.encode("ascii"))

    @synchronized  # type: ignore[arg-type]  # decorator is typed against the base Monoprice class
    def set_baud_rate(self, baud: int) -> bool:
        """Switch the amplifier and local port to `baud`.

        Only the six enumerated rates the firmware documents are accepted;
        anything else is rejected without touching the port. Returns True
        once the new rate is confirmed with a status query, False if the
        amp didn't respond at the new rate (the port is left at its
        original rate in that case).
        """
        if baud not in SUPPORTED_BAUD_RATES:
            raise ValueError(f"Unsupported baud rate: {baud}")

        original_baud = self._port.baudrate
        if baud == original_baud:
            return True

        try:
            self._process_request(_format_set_baud_rate(baud))
        except Exception as err:  # noqa: BLE001 - hardware I/O, log and fall through
            _LOGGER.warning("Baud rate switch request failed: %s", err)

        self._port.baudrate = baud
        self._port.reset_input_buffer()
        self._port.reset_output_buffer()

        try:
            self.zone_status(11)
            return True
        except Exception:  # noqa: BLE001 - confirm-by-query, any failure means revert
            _LOGGER.warning(
                "Amplifier did not respond at %d baud; reverting to %d",
                baud,
                original_baud,
            )
            self._port.baudrate = original_baud
            self._port.reset_input_buffer()
            self._port.reset_output_buffer()
            return False


def get_monoprice_extended(port_url: str) -> MonopriceExtended:
    """Return an extended synchronous Monoprice client for `port_url`."""
    return MonopriceExtended(port_url, RLock())
