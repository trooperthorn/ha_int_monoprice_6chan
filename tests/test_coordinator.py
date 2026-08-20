"""Tests for coordinator.py's baud negotiation, discovery, and refresh-merge
logic, using lightweight `homeassistant` stubs (see ha_stubs.py) instead of
a full framework install.
"""
import asyncio
import os
import sys
import unittest
from dataclasses import dataclass
from unittest.mock import MagicMock

sys.path.insert(0, os.path.dirname(__file__))
import ha_stubs  # noqa: E402

ha_stubs.install()

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from custom_components.monoprice_custom.coordinator import (  # noqa: E402
    DEFAULT_TARGET_BAUD,
    MonopriceCoordinator,
)


@dataclass
class FakeZoneStatus:
    zone: int
    power: bool = True
    volume: int = 20
    source: int = 1


def run(coro):
    return asyncio.run(coro)


class FakeHass:
    async def async_add_executor_job(self, func, *args):
        return func(*args)


class TestBaudNegotiation(unittest.TestCase):
    def _make_coordinator(self, options=None):
        api = MagicMock()
        api._port.baudrate = 9600
        entry = MagicMock()
        entry.options = options or {}
        coordinator = MonopriceCoordinator(FakeHass(), api, entry)
        return coordinator, api

    def test_target_baud_rate_defaults(self):
        coordinator, _ = self._make_coordinator()
        self.assertEqual(coordinator.target_baud_rate, DEFAULT_TARGET_BAUD)

    def test_target_baud_rate_honors_options(self):
        coordinator, _ = self._make_coordinator(options={"baud_rate": 115200})
        self.assertEqual(coordinator.target_baud_rate, 115200)

    def test_target_baud_rate_rejects_unsupported_value(self):
        # An unsupported/corrupt stored option falls back to the default
        # instead of being sent to the amp as-is.
        coordinator, _ = self._make_coordinator(options={"baud_rate": 4800})
        self.assertEqual(coordinator.target_baud_rate, DEFAULT_TARGET_BAUD)

    def test_optimize_sync_skips_when_already_at_target_and_confirmed(self):
        coordinator, api = self._make_coordinator(options={"baud_rate": 9600})
        api._port.baudrate = 9600
        api.zone_status.return_value = FakeZoneStatus(zone=11)
        coordinator._async_optimize_baud_rate_sync()
        api.set_baud_rate.assert_not_called()
        api.zone_status.assert_called_once_with(11)

    def test_optimize_sync_upgrades_when_amp_already_responds_at_current_rate(self):
        coordinator, api = self._make_coordinator(options={"baud_rate": 38400})
        api._port.baudrate = 9600
        api.zone_status.return_value = FakeZoneStatus(zone=11)
        coordinator._async_optimize_baud_rate_sync()
        api.set_baud_rate.assert_called_once_with(38400)

    def test_optimize_sync_reverifies_even_when_local_attribute_matches_target(self):
        # Regression test: if the local port object's baudrate attribute
        # already reads as the target (e.g. after a mid-session reconnect
        # that never reset it) but the amp itself fell back to 9600 (power
        # cycle), the coordinator must notice and renegotiate instead of
        # trusting the stale attribute and wedging silently.
        coordinator, api = self._make_coordinator(options={"baud_rate": 38400})
        api._port.baudrate = 38400  # stale: amp actually reset to 9600

        def zone_status_side_effect(zone):
            if api._port.baudrate == 38400:
                raise Exception("timeout")
            return FakeZoneStatus(zone=zone)

        api.zone_status.side_effect = zone_status_side_effect
        coordinator._async_optimize_baud_rate_sync()
        # Local port was reset to the power-on default before negotiating up.
        self.assertEqual(api._port.reset_input_buffer.call_count, 1)
        api.set_baud_rate.assert_called_once_with(38400)


class TestActiveUnitDiscovery(unittest.TestCase):
    def test_discovers_only_units_that_respond(self):
        api = MagicMock()
        entry = MagicMock()
        entry.options = {}
        coordinator = MonopriceCoordinator(FakeHass(), api, entry)

        def zone_status_side_effect(zone):
            if zone == 21:
                return FakeZoneStatus(zone=21)
            if zone == 31:
                return None  # unit 3 not physically present
            return FakeZoneStatus(zone=zone)

        api.zone_status.side_effect = zone_status_side_effect
        run(coordinator._async_discover_active_units())
        self.assertEqual(coordinator.active_units, [1, 2])

    def test_no_expansion_units_present(self):
        api = MagicMock()
        entry = MagicMock()
        entry.options = {}
        coordinator = MonopriceCoordinator(FakeHass(), api, entry)
        api.zone_status.side_effect = lambda zone: None
        run(coordinator._async_discover_active_units())
        self.assertEqual(coordinator.active_units, [1])


class TestZoneRefreshMerge(unittest.TestCase):
    def test_refresh_zone_merges_into_existing_data_without_dropping_other_zones(self):
        api = MagicMock()
        entry = MagicMock()
        entry.options = {}
        coordinator = MonopriceCoordinator(FakeHass(), api, entry)
        coordinator.data = {11: FakeZoneStatus(zone=11, volume=10), 12: FakeZoneStatus(zone=12, volume=5)}

        api.zone_status.return_value = FakeZoneStatus(zone=11, volume=25)
        run(coordinator.async_refresh_zone(11))

        self.assertEqual(coordinator.data[11].volume, 25)
        self.assertEqual(coordinator.data[12].volume, 5)  # untouched

    def test_refresh_zone_ignores_none_status(self):
        api = MagicMock()
        entry = MagicMock()
        entry.options = {}
        coordinator = MonopriceCoordinator(FakeHass(), api, entry)
        coordinator.data = {11: FakeZoneStatus(zone=11, volume=10)}
        api.zone_status.return_value = None
        run(coordinator.async_refresh_zone(11))
        self.assertEqual(coordinator.data[11].volume, 10)


if __name__ == "__main__":
    unittest.main()
