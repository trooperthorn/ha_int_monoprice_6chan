"""Lifecycle tests for the single-owner Monoprice gateway."""

from __future__ import annotations

import asyncio
import importlib
import sys
import threading
import time
import unittest
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import patch

PACKAGE_ROOT = Path(__file__).parents[1] / "custom_components" / "monoprice_custom"
package = sys.modules.setdefault("monoprice_custom", ModuleType("monoprice_custom"))
package.__path__ = [str(PACKAGE_ROOT)]

try:
    import homeassistant.core
except ModuleNotFoundError:
    homeassistant = sys.modules.setdefault("homeassistant", ModuleType("homeassistant"))
    homeassistant.__path__ = []
    ha_core = sys.modules.setdefault(
        "homeassistant.core", ModuleType("homeassistant.core")
    )
    ha_core.HomeAssistant = object

gateway_module = importlib.import_module("monoprice_custom.gateway")
serialx = gateway_module.serialx


class FakeHass:
    """Run executor jobs on worker threads like Home Assistant."""

    async def async_add_executor_job(self, function, *args):
        return await asyncio.to_thread(function, *args)


class BlockingApi:
    """API fake that exposes close ordering."""

    def __init__(self) -> None:
        self.current_baud_rate = 9600
        self.started = threading.Event()
        self.release = threading.Event()
        self.closed = False

    def block(self) -> str:
        self.started.set()
        self.release.wait(1)
        return "complete"

    def close(self) -> None:
        self.closed = True


class SerializingApi:
    """API fake that measures concurrent client access."""

    def __init__(self) -> None:
        self.current_baud_rate = 9600
        self.active = 0
        self.maximum_active = 0
        self.guard = threading.Lock()

    def operation(self) -> None:
        with self.guard:
            self.active += 1
            self.maximum_active = max(self.maximum_active, self.active)
        time.sleep(0.03)
        with self.guard:
            self.active -= 1

    def close(self) -> None:
        return


class RecoveryApi:
    """API fake for the bounded 9600-first recovery sequence."""

    def __init__(self) -> None:
        self.current_baud_rate = 57600
        self.probes: list[int] = []
        self.switches: list[int] = []

    def probe_baud_rate(self, baud: int) -> bool:
        self.probes.append(baud)
        self.current_baud_rate = baud
        return baud == 9600

    def set_baud_rate(self, baud: int) -> bool:
        self.switches.append(baud)
        self.current_baud_rate = baud
        return True

    def close(self) -> None:
        return


class TestGatewayLifecycle(unittest.IsolatedAsyncioTestCase):
    async def test_close_drains_inflight_io_and_rejects_new_work(self) -> None:
        api = BlockingApi()
        gateway = gateway_module.MonopriceGateway(FakeHass(), api)
        operation = asyncio.create_task(gateway.async_execute("block"))
        await asyncio.to_thread(api.started.wait, 1)

        close = asyncio.create_task(gateway.async_close())
        await asyncio.sleep(0)
        with self.assertRaises(gateway_module.GatewayClosedError):
            await gateway.async_execute("block")
        self.assertFalse(close.done())

        api.release.set()
        self.assertEqual(await operation, "complete")
        await close
        self.assertTrue(api.closed)
        self.assertEqual(
            gateway.connection_state, gateway_module.ConnectionState.CLOSED
        )

    async def test_operations_are_serialized(self) -> None:
        api = SerializingApi()
        gateway = gateway_module.MonopriceGateway(FakeHass(), api)
        await asyncio.gather(
            gateway.async_execute("operation"),
            gateway.async_execute("operation"),
        )
        self.assertEqual(api.maximum_active, 1)

    async def test_recovery_probes_9600_before_negotiating_target(self) -> None:
        # auto=False is the direct path: go to the requested rate in one move.
        api = RecoveryApi()
        gateway = gateway_module.MonopriceGateway(FakeHass(), api, 57600)

        baud = await gateway.async_ensure_link(38400, auto=False)

        self.assertEqual(baud, 38400)
        self.assertEqual(api.probes, [9600])
        self.assertEqual(api.switches, [38400])
        self.assertEqual(gateway.reconnect_count, 1)

    async def test_recovery_climbs_one_step_when_automatic(self) -> None:
        # Same starting point, automatic: one step up from where it was found,
        # not a leap to the ceiling.
        api = RecoveryApi()
        gateway = gateway_module.MonopriceGateway(FakeHass(), api, 57600)

        baud = await gateway.async_ensure_link(38400, auto=True)

        self.assertEqual(baud, 19200)
        self.assertEqual(api.switches, [19200])


class TestCommandFloor(unittest.IsolatedAsyncioTestCase):
    """The lock stops commands overlapping; it does not space them apart.

    pyxantech enforces a minimum interval on every series it supports to keep
    the amplifier from timing out when commands arrive faster than it answers.
    """

    @staticmethod
    def _gateway():
        api = SimpleNamespace(current_baud_rate=9600, noop=lambda: None)
        return gateway_module.MonopriceGateway(FakeHass(), api), api

    async def test_consecutive_commands_are_spaced(self) -> None:
        gateway, api = self._gateway()
        with patch.object(gateway_module, "MIN_COMMAND_INTERVAL", 0.05):
            await gateway._async_locked_call(api.noop)
            started = time.monotonic()
            await gateway._async_locked_call(api.noop)
            elapsed = time.monotonic() - started
        self.assertGreaterEqual(elapsed, 0.05)

    async def test_first_command_is_not_delayed(self) -> None:
        gateway, api = self._gateway()
        with patch.object(gateway_module, "MIN_COMMAND_INTERVAL", 0.5):
            started = time.monotonic()
            await gateway._async_locked_call(api.noop)
            elapsed = time.monotonic() - started
        self.assertLess(elapsed, 0.5)

    async def test_a_failed_command_still_spaces_the_next_one(self) -> None:
        # The floor exists to protect the amplifier, so a command that raised
        # must not let the next one follow immediately.
        gateway, api = self._gateway()

        def boom():
            raise OSError("no reply")

        with patch.object(gateway_module, "MIN_COMMAND_INTERVAL", 0.05):
            with self.assertRaises(OSError):
                await gateway._async_locked_call(boom)
            started = time.monotonic()
            await gateway._async_locked_call(api.noop)
            elapsed = time.monotonic() - started
        self.assertGreaterEqual(elapsed, 0.05)


class TestLinkSpeedNegotiation(unittest.TestCase):
    """The configured rate is a ceiling to climb to, not one to leap at.

    The amplifier changes speed on receipt and never acknowledges, so a rate
    the wiring cannot carry leaves it unreachable until it loses power. That
    asymmetry is why automatic mode climbs one step at a time and why a rate
    that failed is never tried again.
    """

    @staticmethod
    def _gateway():
        api = SimpleNamespace(current_baud_rate=9600)
        return gateway_module.MonopriceGateway(FakeHass(), api)

    def test_automatic_mode_climbs_one_step(self):
        gw = self._gateway()
        self.assertEqual(gw._next_rate(9600, 230400, auto=True), 19200)
        self.assertEqual(gw._next_rate(19200, 230400, auto=True), 38400)
        self.assertEqual(gw._next_rate(115200, 230400, auto=True), 230400)

    def test_automatic_mode_stops_at_the_ceiling(self):
        gw = self._gateway()
        self.assertEqual(gw._next_rate(9600, 19200, auto=True), 19200)
        self.assertEqual(gw._next_rate(19200, 19200, auto=True), 19200)
        # Already above what was asked for: do not climb further.
        self.assertEqual(gw._next_rate(38400, 19200, auto=True), 19200)

    def test_manual_mode_goes_straight_there(self):
        # Someone who picked a rate means that rate, trap and all.
        gw = self._gateway()
        self.assertEqual(gw._next_rate(9600, 230400, auto=False), 230400)

    def test_a_proven_rate_is_returned_to_directly(self):
        # Climbing one step per link-up would take four polls to get back to a
        # rate already known to work on this cabling.
        gw = self._gateway()
        gw.proven_baud = 115200
        self.assertEqual(gw._next_rate(9600, 230400, auto=True), 115200)

    def test_a_failed_rate_caps_everything_below_it(self):
        gw = self._gateway()
        gw.failed_baud = 115200
        self.assertEqual(gw._ceiling(230400), 57600)
        self.assertEqual(gw._next_rate(57600, 230400, auto=True), 57600)

    def test_a_proven_rate_never_exceeds_a_failed_one(self):
        gw = self._gateway()
        gw.proven_baud = 115200
        gw.failed_baud = 38400
        self.assertEqual(gw._next_rate(9600, 230400, auto=True), 19200)

    def test_failing_at_9600_leaves_nothing_to_fall_back_to(self):
        gw = self._gateway()
        gw.failed_baud = 9600
        self.assertEqual(gw._ceiling(230400), 9600)


class TestFailedSwitchRecovery(unittest.IsolatedAsyncioTestCase):
    """A switch that is not confirmed must be searched for, not abandoned."""

    @staticmethod
    def _gateway(*, confirms: bool, reachable_after: int | None):
        """Model an amplifier that really does change speed on receipt.

        `confirms` is whether the switch is acknowledged; `reachable_after` is
        the rate it can actually be reached at once it has moved, or None when
        the wiring cannot carry the new speed at all.
        """
        state = {"at": 9600}

        def set_baud_rate(baud):
            state["at"] = reachable_after
            return confirms

        api = SimpleNamespace(
            current_baud_rate=9600,
            probe_baud_rate=lambda b: b == state["at"],
            set_baud_rate=set_baud_rate,
        )
        return gateway_module.MonopriceGateway(FakeHass(), api), api

    async def test_an_unconfirmed_switch_relocates_the_amplifier(self):
        # The amplifier did move and is reachable there; the confirmation was
        # simply unlucky, so the link is fine.
        gw, _ = self._gateway(confirms=False, reachable_after=19200)
        baud = await gw.async_ensure_link(19200, auto=True)
        self.assertEqual(baud, 19200)
        self.assertEqual(gw.failed_baud, 19200, "recorded, so it is not retried")

    async def test_an_unreachable_amplifier_says_how_to_recover(self):
        # The wiring cannot carry the new speed, so the amplifier is gone until
        # it loses power. The error has to say that, not just "timed out".
        gw, _ = self._gateway(confirms=False, reachable_after=None)
        with self.assertRaises(serialx.SerialTimeoutException) as caught:
            await gw.async_ensure_link(19200, auto=True)
        message = str(caught.exception)
        self.assertIn("30 seconds", message)
        self.assertIn("9600", message)
        self.assertEqual(gw.failed_baud, 19200)

    async def test_a_confirmed_switch_is_remembered_as_proven(self):
        gw, _ = self._gateway(confirms=True, reachable_after=19200)
        baud = await gw.async_ensure_link(19200, auto=True)
        self.assertEqual(baud, 19200)
        self.assertEqual(gw.proven_baud, 19200)
        self.assertIsNone(gw.failed_baud)


if __name__ == "__main__":
    unittest.main()
