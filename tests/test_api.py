"""Unit tests for the RS-232 command formatting in api.py.

These test the pure wire-protocol framing against the Monoprice Multizone
Controller RS-232 spec directly, without needing Home Assistant or real
hardware. Entity/coordinator behavior needs `pytest-homeassistant-custom-
component` and belongs in a follow-up once that harness is wired up (see
README "Testing").
"""

import importlib
import sys
import unittest
from pathlib import Path
from threading import RLock
from types import ModuleType, SimpleNamespace
from unittest.mock import Mock, patch

PACKAGE_ROOT = Path(__file__).parents[1] / "custom_components" / "monoprice_custom"
package = ModuleType("monoprice_custom")
package.__path__ = [str(PACKAGE_ROOT)]
sys.modules.setdefault("monoprice_custom", package)

api = importlib.import_module("monoprice_custom.api")


class TestCommandFraming(unittest.TestCase):
    def test_set_pa_on(self):
        self.assertEqual(api._format_set_pa(11, True), b"<11PA01\r")

    def test_set_pa_off(self):
        self.assertEqual(api._format_set_pa(11, False), b"<11PA00\r")

    def test_set_dnd_on(self):
        self.assertEqual(api._format_set_dnd(21, True), b"<21DT01\r")

    def test_rename_source_pads_to_eight_chars(self):
        self.assertEqual(api._format_rename_source(1, "AppleTV "), b"1<AppleTV \r")

    def test_set_keypad_message(self):
        self.assertEqual(api._format_set_keypad_message("Living  "), b"M<Living  \r")

    def test_baud_rate_command_has_no_dollar_prefix(self):
        # Regression test: the coordinator used to send "$<{baud}\r", which
        # does not match the documented fixed-token format.
        cmd = api._format_set_baud_rate(38400)
        self.assertEqual(cmd, b"<38400\r")
        self.assertNotIn(b"$", cmd)

    def test_only_documented_baud_rates_are_supported(self):
        self.assertEqual(
            api.SUPPORTED_BAUD_RATES, (9600, 19200, 38400, 57600, 115200, 230400)
        )

    def test_zone_field_status_query(self):
        self.assertEqual(api._format_zone_field_status(11, "VO"), b"?11VO\r")


class TestBaudSwitch(unittest.TestCase):
    def test_switch_does_not_wait_for_reply_at_old_baud(self):
        client = object.__new__(api.MonopriceExtended)
        client._lock = RLock()
        client._port = SimpleNamespace(
            baudrate=9600,
            reset_input_buffer=Mock(),
            reset_output_buffer=Mock(),
        )
        client._send_request = Mock()
        client.zone_status = Mock(return_value=SimpleNamespace(zone=11))
        client._process_request = Mock(
            side_effect=AssertionError("must not read at old baud")
        )

        self.assertTrue(client.set_baud_rate(38400))
        client._send_request.assert_called_once_with(b"<38400\r")
        client._process_request.assert_not_called()
        self.assertEqual(client._port.baudrate, 38400)

    def test_settles_before_clearing_the_stale_echo(self):
        # The amplifier switches mid-reply, so the tail of its echo arrives at
        # the old rate after the switch. Clearing before it lands leaves those
        # bytes to be read as the confirmation, which on hardware made the
        # switch report failure while the amplifier had already moved.
        client = object.__new__(api.MonopriceExtended)
        client._lock = RLock()
        manager = Mock()
        client._port = SimpleNamespace(
            baudrate=9600,
            reset_input_buffer=manager.reset_input,
            reset_output_buffer=manager.reset_output,
        )
        client._send_request = manager.send
        client.zone_status = Mock(return_value=SimpleNamespace(zone=11))

        with patch.object(api, "sleep", manager.sleep):
            self.assertTrue(client.set_baud_rate(38400))

        order = [name for name, _, _ in manager.mock_calls]
        self.assertLess(order.index("sleep"), order.index("reset_input"))
        self.assertLess(order.index("send"), order.index("sleep"))
        manager.sleep.assert_called_once_with(api.BAUD_SETTLE)


class TestReplyFraming(unittest.TestCase):
    """A reply that is not a control write spans two EOL sequences.

    Reading only the first leaves the rest in the buffer, where the next
    command reads it as its own answer; see docs/protocol.md.
    """

    def _client(self):
        client = object.__new__(api.MonopriceExtended)
        client._lock = RLock()
        client._process_request = Mock(return_value="")
        return client

    def test_rename_source_reads_both_frames(self):
        client = self._client()
        client.rename_source(1, "AppleTV")
        self.assertEqual(
            client._process_request.call_args.kwargs["num_eols_to_read"], 2
        )

    def test_set_keypad_message_reads_both_frames(self):
        client = self._client()
        client.set_keypad_message("Living")
        self.assertEqual(
            client._process_request.call_args.kwargs["num_eols_to_read"], 2
        )

    def test_zone_field_status_reads_both_frames(self):
        client = self._client()
        client.zone_field_status(11, "VO")
        self.assertEqual(
            client._process_request.call_args.kwargs["num_eols_to_read"], 2
        )

    def test_send_raw_drains_what_it_could_not_predict(self):
        # An arbitrary command's frame count is unknown before it is sent, so
        # send_raw reads one frame and then drains the rest.
        client = self._client()
        client._process_request = Mock(return_value="?11\r\n#")
        client._port = SimpleNamespace(
            in_waiting=11,
            read=Mock(return_value=b">1100000000120707100100\r\r\n#"),
        )
        result = client.send_raw("?11")
        self.assertIn(">11", result)
        client._port.read.assert_called_once_with(11)

    def test_send_raw_returns_first_frame_when_nothing_follows(self):
        client = self._client()
        client._process_request = Mock(return_value="<11VO12\r\n#")
        client._port = SimpleNamespace(in_waiting=0, read=Mock())
        self.assertEqual(client.send_raw("<11VO12"), "<11VO12\r\n#")
        client._port.read.assert_not_called()


class TestKeypadTextValidation(unittest.TestCase):
    """The amplifier answers a bad index or non-ASCII with Command Error."""

    def _client(self):
        client = object.__new__(api.MonopriceExtended)
        client._lock = RLock()
        client._process_request = Mock(return_value="")
        return client

    def test_source_index_below_range_is_rejected(self):
        with self.assertRaises(ValueError):
            self._client().rename_source(0, "Nope")

    def test_source_index_above_range_is_rejected(self):
        with self.assertRaises(ValueError):
            self._client().rename_source(7, "Nope")

    def test_rejected_index_is_never_sent(self):
        client = self._client()
        with self.assertRaises(ValueError):
            client.rename_source(9, "Nope")
        client._process_request.assert_not_called()

    def test_non_ascii_source_name_is_rejected(self):
        with self.assertRaises(ValueError):
            self._client().rename_source(1, "Caf\u00e9")

    def test_non_ascii_keypad_message_is_rejected(self):
        with self.assertRaises(ValueError):
            self._client().set_keypad_message("Caf\u00e9")

    def test_non_ascii_raw_command_is_rejected(self):
        client = self._client()
        with self.assertRaises(ValueError):
            client.send_raw("<11VO\u00e912")
        client._process_request.assert_not_called()

    def test_display_name_pads_and_truncates_to_eight(self):
        self.assertEqual(api._display_name("AppleTV"), "AppleTV ")
        self.assertEqual(api._display_name("LongerThanEight"), "LongerTh")


class TestRejectionHandling(unittest.TestCase):
    """A rejection is a resync point, not something to parse past.

    "Command Error." spans two EOL sequences. Parsing on would read the second
    one as some later command's reply, which is the desync the rest of this
    module is built to avoid.
    """

    def _client(self, response, pending=b""):
        client = object.__new__(api.MonopriceExtended)
        client._lock = RLock()
        client._port = SimpleNamespace(
            in_waiting=len(pending), read=Mock(return_value=pending)
        )
        return client

    def test_rejection_in_the_first_frame_raises(self):
        client = self._client("")
        with (
            patch.object(api, "sleep"),
            self.assertRaises(api.MonopriceCommandError),
        ):
            client._checked(b"?1\r", "?1\r\n#\r\nCommand Error.\r\n#", drain=True)

    def test_a_clean_reply_passes_through_untouched(self):
        client = self._client("")
        reply = "?11\r\n#>1100000000120707100100\r\r\n#"
        self.assertEqual(client._checked(b"?11\r", reply, drain=True), reply)

    def test_the_rejection_message_names_the_command(self):
        client = self._client("")
        with (
            patch.object(api, "sleep"),
            self.assertRaises(api.MonopriceCommandError) as caught,
        ):
            client._checked(b"<99VO10\r", "\r\nCommand Error.\r\n#", drain=False)
        self.assertIn("<99VO10", str(caught.exception))

    def test_drain_pulls_the_rest_of_the_rejection_off_the_line(self):
        # Leaving the second frame queued is exactly the desync being avoided.
        client = self._client("", pending=b"\r\nCommand Error.\r\n#")
        with (
            patch.object(api, "sleep"),
            self.assertRaises(api.MonopriceCommandError),
        ):
            client._checked(b"?1\r", "?1\r\n#Command Error.", drain=True)
        client._port.read.assert_called_once()


class TestProbeSettle(unittest.TestCase):
    """The probe must let the wake's reply land before clearing.

    Without this, a probe on a freshly opened port fails at every rate even
    though the amplifier is answering: the wake's reply is still arriving when
    the buffer is cleared, so the status query reads it instead. Observed as
    0/6 rates found on a fresh port, 8/8 after.
    """

    def _client(self):
        client = object.__new__(api.MonopriceExtended)
        client._lock = RLock()
        return client

    def test_settles_between_wake_and_query(self):
        client = self._client()
        manager = Mock()
        client._port = SimpleNamespace(
            baudrate=9600,
            reset_input_buffer=manager.reset_input,
            reset_output_buffer=manager.reset_output,
        )
        client._send_request = manager.wake
        client.zone_status = Mock(return_value=SimpleNamespace(zone=11))

        with patch.object(api, "sleep", manager.sleep):
            self.assertTrue(client.probe_baud_rate(9600))

        order = [name for name, _, _ in manager.mock_calls]
        self.assertLess(order.index("wake"), order.index("sleep"))
        # A clear after the settle is what actually discards the wake's reply.
        self.assertGreater(
            len([n for n in order[order.index("sleep") :] if n == "reset_input"]), 0
        )
        manager.sleep.assert_called_once_with(api.PROBE_SETTLE)

    def test_unsupported_rate_is_rejected_before_touching_the_port(self):
        client = self._client()
        client._port = SimpleNamespace(baudrate=9600)
        with self.assertRaises(ValueError):
            client.probe_baud_rate(4800)
        self.assertEqual(client._port.baudrate, 9600)


if __name__ == "__main__":
    unittest.main()
