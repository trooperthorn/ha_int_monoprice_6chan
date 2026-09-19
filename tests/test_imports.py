"""Every module in the integration must import.

A platform whose module raises on import is not a failing entity, it is a
missing platform: Home Assistant logs the failure during setup and carries on
without it. Nothing else in this suite imports `switch.py`, `text.py`,
`remote.py`, `sensor.py` or `diagnostics.py`, so an import-time mistake in any
of them - a name taken from the wrong module, say - reaches a release with the
whole gate green. This is the cheapest guard against that.
"""

from __future__ import annotations

import importlib

import pytest

# Not `importorskip("homeassistant")`: test_gateway.py stubs a bare
# `homeassistant` module into sys.modules so it can run without the
# harness, and collection order means that stub can already be in place
# here. Gate on a real submodule instead.
pytest.importorskip("homeassistant.config_entries")

MODULES = (
    "api",
    "config_flow",
    "const",
    "coordinator",
    "device",
    "diagnostics",
    "gateway",
    "media_player",
    "number",
    "remote",
    "sensor",
    "serial",
    "services",
    "switch",
    "text",
    "zones",
)


@pytest.mark.parametrize("module", MODULES)
def test_module_imports(module: str) -> None:
    importlib.import_module(f"custom_components.monoprice_custom.{module}")


def test_every_module_is_covered() -> None:
    """Fail if a new module is added without being listed above."""
    from pathlib import Path

    package = Path(__file__).parents[1] / "custom_components" / "monoprice_custom"
    on_disk = {
        path.stem for path in package.glob("*.py") if path.stem not in {"__init__"}
    }
    assert on_disk == set(MODULES), (
        f"modules not covered by test_module_imports: {sorted(on_disk - set(MODULES))}"
    )
