"""Unit tests for the RS-232 command formatting in api.py.

These test the pure wire-protocol framing against the Monoprice Multizone
Controller RS-232 spec directly, without needing Home Assistant or real
hardware. Entity/coordinator behavior needs `pytest-homeassistant-custom-
component` and belongs in a follow-up once that harness is wired up (see
README "Testing").
"""
import os
import sys
import unittest

sys.path.insert(
    0, os.path.join(os.path.dirname(__file__), "..", "custom_components", "monoprice_custom")
)

import api  # noqa: E402


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


if __name__ == "__main__":
    unittest.main()
