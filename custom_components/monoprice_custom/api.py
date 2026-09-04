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

from .serial import SUPPORTED_BAUD_RATES

_LOGGER = logging.getLogger(__name__)


def _format_set_pa(zone: int, pa: bool) -> bytes:
    return "<{}PA{}\r".format(zone, "01" if pa else "00").encode()


def _format_set_dnd(zone: int, dnd: bool) -> bytes:
    return "<{}DT{}\r".format(zone, "01" if dnd else "00").encode()


def _format_rename_source(index: int, name: str) -> bytes:
    return f"{index}<{name[:8]:8}\r".encode("ascii")


def _format_set_keypad_message(name: str) -> bytes:
    return f"M<{name[:8]:8}\r".encode("ascii")


def _format_set_baud_rate(baud: int) -> bytes:
    return f"<{baud}\r".encode()


def _format_zone_field_status(zone: int, field: str) -> bytes:
    return f"?{zone}{field}\r".encode()


class MonopriceExtended(Monoprice):
    """Monoprice client extended with PA/DND/rename/baud commands."""

    @synchronized
    def wake(self) -> None:
        """Send the documented wake sequence without awaiting a reply."""
        self._send_request(b"\r\n")

    @synchronized
    def close(self) -> None:
        """Close the owned serial interface."""
        if not self._port.closed:
            self._port.close()

    @property
    def current_baud_rate(self) -> int:
        """Return the local serial interface's current baud rate."""
        return int(self._port.baudrate)

    @synchronized
    def probe_baud_rate(self, baud: int) -> bool:
        """Set the local rate and verify Zone 11 without changing the amplifier."""
        if baud not in SUPPORTED_BAUD_RATES:
            raise ValueError(f"Unsupported baud rate: {baud}")
        self._port.baudrate = baud
        self._port.reset_input_buffer()
        self._port.reset_output_buffer()
        self._send_request(b"\r\n")
        try:
            status = self.zone_status(11)
        except Exception:  # noqa: BLE001 - a failed probe is a bounded state
            return False
        return status is not None and status.zone == 11

    @synchronized
    def set_pa(self, zone: int, pa: bool) -> None:
        """Turn the zone's paging (PA) override on or off."""
        self._process_request(_format_set_pa(zone, pa))

    @synchronized
    def set_dnd(self, zone: int, dnd: bool) -> None:
        """Turn the zone's do-not-disturb (DT) flag on or off."""
        self._process_request(_format_set_dnd(zone, dnd))

    @synchronized
    def rename_source(self, index: int, name: str) -> None:
        """Rename source `index` (1-6) on the keypad displays.

        `name` is padded/truncated to the 8 ASCII characters the hardware
        requires.
        """
        self._process_request(_format_rename_source(index, name.ljust(8)))

    @synchronized
    def set_keypad_message(self, name: str) -> None:
        """Set the boot welcome message shown on zone keypads."""
        self._process_request(_format_set_keypad_message(name.ljust(8)))

    @synchronized
    def zone_field_status(self, zone: int, field: str) -> str:
        """Query a single status field (e.g. "VO") instead of the full block.

        Cuts the amount of data read/parsed when only one value changed,
        lowering the latency between an on-amp change and its reflection
        in Home Assistant.
        """
        return self._process_request(_format_zone_field_status(zone, field))

    @synchronized
    def send_raw(self, command: str) -> str:
        """Send an arbitrary already-formatted command, locked against polling."""
        if not command.endswith("\r"):
            command += "\r"
        return self._process_request(command.encode("ascii"))

    @synchronized
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

        # Does not reply at the old rate after this; see docs/protocol.md.
        self._send_request(_format_set_baud_rate(baud))

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
