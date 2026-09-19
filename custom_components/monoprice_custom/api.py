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
from time import sleep
from typing import Final

from pymonoprice import Monoprice, synchronized

from .serial import SUPPORTED_BAUD_RATES

_LOGGER = logging.getLogger(__name__)

# The keypad display strings are a fixed 8 ASCII characters.
NAME_LENGTH: Final = 8
SOURCE_INDEXES: Final = range(1, 7)
# A query and the "Done."/"Command Error." acknowledgements are both framed
# as two EOL sequences, unlike a control command's single one; see
# docs/protocol.md.
REPLY_EOLS: Final = 2
# How long to wait for any frames beyond the first when the reply length is
# not known ahead of the send, as with send_raw.
DRAIN_SETTLE: Final = 0.15
# How long to let the line go quiet after the amplifier changes rate. It
# switches mid-reply, so the tail of its echo is still arriving at the old
# rate; clearing before it lands leaves those bytes to be read as the
# confirmation. Measured threshold on a 10761 is 0.05s.
BAUD_SETTLE: Final = 0.25
# The wake sent before a probe draws a reply of its own. Clearing the
# buffer before it has landed leaves those bytes to be read as the status
# reply, which makes a probe fail on a port that has just been opened even
# when the amplifier is answering perfectly.
PROBE_SETTLE: Final = 0.15
# The amplifier's rejection reply. It is framed as two EOL sequences, so a
# control write that reads only its own echo leaves the rejection behind to
# be read as the next command's answer.
COMMAND_ERROR: Final = "Command Error."


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


class MonopriceCommandError(Exception):
    """The amplifier answered a command with "Command Error.".

    Raised rather than parsed past: the rejection occupies frames the
    caller was not expecting, so continuing would read them as some later
    command's reply. Callers treat it as a resync point.
    """


def _display_name(name: str) -> str:
    """Pad or truncate to the hardware's 8 ASCII characters.

    The amplifier accepts only 7-bit ASCII here. Encoding a non-ASCII name
    would raise ``UnicodeEncodeError`` from deep inside the formatter, so it
    is rejected up front as a value error the caller can translate.
    """
    padded = name[:NAME_LENGTH].ljust(NAME_LENGTH)
    try:
        padded.encode("ascii")
    except UnicodeEncodeError as err:
        raise ValueError(f"Keypad text must be ASCII only, got {name!r}") from err
    return padded


class MonopriceExtended(Monoprice):
    """Monoprice client extended with PA/DND/rename/baud commands."""

    def _process_request(self, request: bytes, num_eols_to_read: int = 1) -> str:
        """Read a reply, refusing to parse past a rejection.

        `api.py` rejects the bad input it knows about before sending, but a
        rejection can also arrive from line noise, a partially written frame,
        or another process on the port. Whatever the cause, the reply is not
        the shape the caller expected and the rest of it is still queued, so
        drain and raise instead of handing back something that parses.
        """
        response = super()._process_request(request, num_eols_to_read)
        return self._checked(request, response, drain=True)

    def _checked(self, request: bytes, response: str, *, drain: bool) -> str:
        """Raise if `response` carries a rejection, draining what follows it.

        A rejection spans two EOL sequences. A command that reads both sees it
        here immediately. A control write reads only its own echo, so the
        rejection is still queued: it surfaces either on the drain below or,
        failing that, prepended to the next command's reply, which is why this
        check runs on every read rather than only the multi-frame ones.
        """
        if COMMAND_ERROR not in response:
            return response
        trailing = self._read_pending() if drain else ""
        raise MonopriceCommandError(
            f"Amplifier rejected {request!r}: {(response + trailing).strip()}"
        )

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
        # Let the wake's own reply arrive before clearing, or the query below
        # reads it instead of the status record.
        sleep(PROBE_SETTLE)
        self._port.reset_input_buffer()
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

    def _read_pending(self) -> str:
        """Return any frames the amplifier sent beyond the ones already read.

        A control command answers with one EOL frame, a query or a
        "Done."/"Command Error." acknowledgement with two, and `?N0` with one
        per zone, so an arbitrary command's reply length is not known before
        it is sent. Draining keeps a leftover frame from being read as the
        answer to whatever is sent next.
        """
        sleep(DRAIN_SETTLE)
        pending = self._port.in_waiting
        if not pending:
            return ""
        return self._port.read(pending).decode("ascii", errors="replace")

    @synchronized
    def rename_source(self, index: int, name: str) -> None:
        """Rename source `index` (1-6) on the keypad displays.

        `name` is padded/truncated to the 8 ASCII characters the hardware
        requires. An index outside 1-6 is rejected here rather than sent: the
        amplifier answers it with "Command Error." and that reply would be
        read as the answer to the next command.
        """
        if index not in SOURCE_INDEXES:
            raise ValueError(f"Source index must be 1-6, got {index}")
        self._process_request(
            _format_rename_source(index, _display_name(name)),
            num_eols_to_read=REPLY_EOLS,
        )

    @synchronized
    def set_keypad_message(self, name: str) -> None:
        """Set the boot welcome message shown on zone keypads."""
        self._process_request(
            _format_set_keypad_message(_display_name(name)),
            num_eols_to_read=REPLY_EOLS,
        )

    @synchronized
    def zone_field_status(self, zone: int, field: str) -> str:
        """Query a single status field (e.g. "VO") instead of the full block.

        Cuts the amount of data read/parsed when only one value changed,
        lowering the latency between an on-amp change and its reflection
        in Home Assistant.
        """
        return self._process_request(
            _format_zone_field_status(zone, field), num_eols_to_read=REPLY_EOLS
        )

    @synchronized
    def send_raw(self, command: str) -> str:
        """Send an arbitrary already-formatted command, locked against polling.

        The caller chooses the command, so the reply's frame count is unknown:
        read the first frame, then drain whatever else arrives.
        """
        if not command.endswith("\r"):
            command += "\r"
        try:
            encoded = command.encode("ascii")
        except UnicodeEncodeError as err:
            raise ValueError(
                f"RS-232 commands must be ASCII only, got {command!r}"
            ) from err
        # The drained tail is checked too: a rejection to a single-frame
        # command lands there, not in the first frame.
        response = self._process_request(encoded) + self._read_pending()
        return self._checked(encoded, response, drain=False)

    @synchronized
    def set_baud_rate(self, baud: int) -> bool:
        """Switch the amplifier and local port to `baud`.

        Only the six enumerated rates the firmware documents are accepted;
        anything else is rejected without touching the port. Returns True
        once the new rate is confirmed with a status query.

        A False return does not mean the amplifier stayed put. It switches on
        receipt and never acknowledges, so an unconfirmed switch leaves it at
        the new rate with the local port put back to the old one. Finding it
        again is `gateway.py::_ensure_link_sync`'s probe loop, which walks the
        supported rates; connecting at the wrong one cannot lock the
        controller, and removing power for 30 seconds forces it back to 9600.
        """
        if baud not in SUPPORTED_BAUD_RATES:
            raise ValueError(f"Unsupported baud rate: {baud}")

        original_baud = self._port.baudrate
        if baud == original_baud:
            return True

        # Does not reply at the old rate after this; see docs/protocol.md.
        self._send_request(_format_set_baud_rate(baud))

        self._port.baudrate = baud
        # Settle before clearing, not after: the echo's tail is still in
        # flight at the old rate and decodes as garbage at the new one, so a
        # reset issued immediately races the bytes it is meant to discard and
        # the confirmation below reads them instead of the status reply.
        sleep(BAUD_SETTLE)
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
