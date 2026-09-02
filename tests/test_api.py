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
from unittest.mock import Mock

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


if __name__ == "__main__":
    unittest.main()
