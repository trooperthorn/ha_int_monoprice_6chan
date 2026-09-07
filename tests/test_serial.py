"""Tests for isolated serial validation and stable endpoint identity."""

from __future__ import annotations

import importlib
import sys
import unittest
from pathlib import Path
from types import ModuleType
from unittest.mock import patch

import serialx

PACKAGE_ROOT = Path(__file__).parents[1] / "custom_components" / "monoprice_custom"
package = sys.modules.setdefault("monoprice_custom", ModuleType("monoprice_custom"))
package.__path__ = [str(PACKAGE_ROOT)]
serial_helpers = importlib.import_module("monoprice_custom.serial")

ZONE_11_RESPONSE = b">1100010000101112100400\r\n#"
# Same frame, only the leading two-digit zone number differs; see docs/protocol.md.
ZONE_21_RESPONSE = b">2100010000101112100400\r\n#"
ZONE_31_RESPONSE = b">3100010000101112100400\r\n#"


class FakePort:
    """Small serialx-compatible validator fake.

    `responding_zones` maps a queried zone number to the canned frame it
    should answer with, so a test can simulate one, two, or three expansion
    units by including 11, 11+21, or 11+21+31.
    """

    def __init__(
        self,
        responding_baud: int | None = None,
        responding_zones: dict[int, bytes] | None = None,
    ) -> None:
        self.responding_baud = responding_baud
        self.responding_zones = responding_zones or {11: ZONE_11_RESPONSE}
        self.baudrate = 9600
        self.closed = True
        self.writes: list[bytes] = []
        self.close_count = 0
        self._reads: list[bytes] = []

    def open(self) -> None:
        self.closed = False

    def close(self) -> None:
        self.closed = True
        self.close_count += 1

    def reset_input_buffer(self) -> None:
        self._reads = []

    def reset_output_buffer(self) -> None:
        return

    def write(self, payload: bytes) -> None:
        self.writes.append(payload)
        if self.baudrate != self.responding_baud:
            return
        for zone, response in self.responding_zones.items():
            if payload == f"?{zone}\r".encode("ascii"):
                self._reads = [b"\r\n#", response]
                return

    def flush(self) -> None:
        return

    def read_until(self, *args, **kwargs) -> bytes:
        if not self._reads:
            raise TimeoutError
        return self._reads.pop(0)


class TestEndpointValidation(unittest.TestCase):
    def test_only_submitted_endpoint_is_opened_and_closed(self) -> None:
        port = FakePort(responding_baud=38400)
        with patch.object(
            serial_helpers.serialx, "serial_for_url", return_value=port
        ) as serial_for_url:
            result = serial_helpers.validate_monoprice_endpoint("socket://amp:23")

        self.assertEqual(result.detected_baud, 38400)
        self.assertEqual(result.detected_units, (1,))
        serial_for_url.assert_called_once()
        self.assertEqual(serial_for_url.call_args.args[0], "socket://amp:23")
        self.assertTrue(port.closed)
        self.assertEqual(port.close_count, 1)
        # Confirming Zone 11, then probing (and failing to find) unit 2's Zone 21.
        self.assertIn(b"?11\r", port.writes)
        self.assertEqual(port.writes[-1], b"?21\r")

    def test_wrong_device_is_closed(self) -> None:
        port = FakePort()
        with (
            patch.object(serial_helpers.serialx, "serial_for_url", return_value=port),
            self.assertRaises(serial_helpers.NotMonopriceDevice),
        ):
            serial_helpers.validate_monoprice_endpoint("COM7", (9600,))
        self.assertTrue(port.closed)

    def test_second_unit_is_detected_when_present(self) -> None:
        port = FakePort(
            responding_baud=9600,
            responding_zones={11: ZONE_11_RESPONSE, 21: ZONE_21_RESPONSE},
        )
        with patch.object(serial_helpers.serialx, "serial_for_url", return_value=port):
            result = serial_helpers.validate_monoprice_endpoint("COM7", (9600,))

        self.assertEqual(result.detected_units, (1, 2))
        # Unit 2 answered, so unit 3 is still probed - it just doesn't answer here.
        self.assertIn(b"?31\r", port.writes)

    def test_third_unit_is_detected_only_after_the_second(self) -> None:
        port = FakePort(
            responding_baud=9600,
            responding_zones={
                11: ZONE_11_RESPONSE,
                21: ZONE_21_RESPONSE,
                31: ZONE_31_RESPONSE,
            },
        )
        with patch.object(serial_helpers.serialx, "serial_for_url", return_value=port):
            result = serial_helpers.validate_monoprice_endpoint("COM7", (9600,))

        self.assertEqual(result.detected_units, (1, 2, 3))

    def test_busy_device_is_reported_without_leaking_port(self) -> None:
        port = FakePort()
        port.open = unittest.mock.Mock(
            side_effect=serialx.SerialException("already open")
        )
        with (
            patch.object(serial_helpers.serialx, "serial_for_url", return_value=port),
            self.assertRaises(serial_helpers.CannotOpenPort),
        ):
            serial_helpers.validate_monoprice_endpoint("COM7")
        self.assertTrue(port.closed)


class TestEndpointIdentity(unittest.TestCase):
    def test_com_port_is_canonicalized_without_path_rewriting(self) -> None:
        self.assertEqual(serial_helpers.canonicalize_endpoint(" com12 "), "COM12")

    def test_manual_serial_url_is_preserved(self) -> None:
        endpoint = "socket://192.0.2.10:23"
        self.assertEqual(serial_helpers.canonicalize_endpoint(endpoint), endpoint)

    def test_usb_serial_identity_survives_path_change(self) -> None:
        first = serial_helpers.endpoint_identity(
            "/dev/ttyUSB0", vid="0403", pid="6001", serial_number="A1"
        )
        second = serial_helpers.endpoint_identity(
            "/dev/ttyUSB4", vid="0403", pid="6001", serial_number="A1"
        )
        self.assertEqual(first, second)
        self.assertEqual(first.kind, "usb_serial")


if __name__ == "__main__":
    unittest.main()
