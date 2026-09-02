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


class FakePort:
    """Small serialx-compatible validator fake."""

    def __init__(self, responding_baud: int | None = None) -> None:
        self.responding_baud = responding_baud
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
        if payload == b"?11\r" and self.baudrate == self.responding_baud:
            self._reads = [b"\r\n#", ZONE_11_RESPONSE]

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
        serial_for_url.assert_called_once()
        self.assertEqual(serial_for_url.call_args.args[0], "socket://amp:23")
        self.assertTrue(port.closed)
        self.assertEqual(port.close_count, 1)
        self.assertEqual(port.writes[-2:], [b"\r\n", b"?11\r"])

    def test_wrong_device_is_closed(self) -> None:
        port = FakePort()
        with (
            patch.object(serial_helpers.serialx, "serial_for_url", return_value=port),
            self.assertRaises(serial_helpers.NotMonopriceDevice),
        ):
            serial_helpers.validate_monoprice_endpoint("COM7", (9600,))
        self.assertTrue(port.closed)

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
