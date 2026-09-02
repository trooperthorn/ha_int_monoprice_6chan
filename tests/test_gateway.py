"""Lifecycle tests for the single-owner Monoprice gateway."""

from __future__ import annotations

import asyncio
import importlib
import sys
import threading
import time
import unittest
from pathlib import Path
from types import ModuleType

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
        api = RecoveryApi()
        gateway = gateway_module.MonopriceGateway(FakeHass(), api, 57600)

        baud = await gateway.async_ensure_link(38400)

        self.assertEqual(baud, 38400)
        self.assertEqual(api.probes, [9600])
        self.assertEqual(api.switches, [38400])
        self.assertEqual(gateway.reconnect_count, 1)


if __name__ == "__main__":
    unittest.main()
