"""Coordinator recovery and expansion rediscovery tests."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import pytest

pytest.importorskip("homeassistant")

from homeassistant.helpers.update_coordinator import UpdateFailed
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.monoprice_custom.const import (
    CONF_BAUD_RATE,
    CONF_LAST_KNOWN_BAUD,
    DOMAIN,
)
from custom_components.monoprice_custom.coordinator import (
    CAUSE_LINK_FAULT,
    CAUSE_POWER_CYCLE,
    CAUSE_UNKNOWN,
    MAX_RETRY_INTERVAL,
    MonopriceCoordinator,
)

pytestmark = pytest.mark.usefixtures("enable_custom_integrations")


@pytest.fixture(autouse=True)
def _no_expansion_probe_spacing():
    """Drop the probe spacing so tests do not wait out a real second."""
    from custom_components.monoprice_custom import coordinator as coordinator_module

    with patch.object(coordinator_module, "EXPANSION_PROBE_SPACING", 0):
        yield


class FakeGateway:
    """Gateway fake with selectable expansion-unit responses."""

    def __init__(self) -> None:
        self.last_known_baud = 9600
        self.last_detected_baud: int | None = None
        self.proven_baud: int | None = None
        self.failed_baud: int | None = None
        self.ensure_calls: list[int] = []
        self.present_units = {1}
        self.fail_with: Exception | None = None

    async def async_ensure_link(self, target: int, auto: bool = True) -> int:
        self.ensure_calls.append(target)
        self.last_known_baud = target
        return target

    async def async_zone_status(self, zone: int):
        if self.fail_with is not None:
            raise self.fail_with
        unit = zone // 10
        if unit not in self.present_units:
            return None
        return SimpleNamespace(zone=zone)

    async def async_wake(self) -> None:
        return


def _coordinator(hass, gateway, **options):
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_LAST_KNOWN_BAUD: 9600},
        options={CONF_BAUD_RATE: 9600} | options,
    )
    entry.add_to_hass(hass)
    return MonopriceCoordinator(hass, gateway, entry)


async def test_repeated_failures_back_off_and_reset_on_success(hass) -> None:
    """A powered-off amplifier must not be swept at the poll interval forever.

    Each failed poll runs the six-rate recovery sweep, which takes longer than
    the default interval, so without backoff the serial line never goes idle.
    """
    gateway = FakeGateway()
    coordinator = _coordinator(hass, gateway)
    gateway.fail_with = TimeoutError("amplifier is off")

    delays = []
    for _ in range(6):
        with pytest.raises(UpdateFailed) as caught:
            await coordinator._async_update_data()
        delays.append(caught.value.retry_after)

    # Doubling from the 5s poll interval, capped.
    assert delays == [5.0, 10.0, 20.0, 40.0, 80.0, 120.0]
    assert delays[-1] == MAX_RETRY_INTERVAL
    assert coordinator.outage_count == 1, "one outage, not one per failed poll"
    assert coordinator.offline_since is not None
    assert coordinator.is_online is False

    gateway.fail_with = None
    await coordinator._async_update_data()
    assert coordinator.consecutive_failures == 0
    assert coordinator.retry_delay is None
    assert coordinator.offline_since is None


@pytest.mark.parametrize(
    ("before", "found", "expected"),
    (
        # Power resets the amplifier to 9600; a link fault leaves it alone.
        (19200, 9600, CAUSE_POWER_CYCLE),
        (38400, 9600, CAUSE_POWER_CYCLE),
        (19200, 19200, CAUSE_LINK_FAULT),
        # At 9600 both look identical, so say so rather than guess.
        (9600, 9600, CAUSE_UNKNOWN),
        (19200, 38400, CAUSE_UNKNOWN),
        (19200, None, CAUSE_UNKNOWN),
    ),
)
async def test_outage_cause_is_inferred_from_the_recovered_rate(
    hass, before: int, found: int | None, expected: str
) -> None:
    """The rate the amplifier is found on separates power loss from a bad cable."""
    gateway = FakeGateway()
    # The link negotiates to the configured target, and it is that negotiated
    # rate the outage is measured against, so the entry has to be configured
    # for `before` rather than the gateway poked directly: the first poll calls
    # async_ensure_link, which would overwrite it.
    coordinator = _coordinator(hass, gateway, **{CONF_BAUD_RATE: before})

    gateway.fail_with = TimeoutError("gone")
    with pytest.raises(UpdateFailed):
        await coordinator._async_update_data()

    gateway.fail_with = None
    gateway.last_detected_baud = found
    await coordinator._async_update_data()

    assert coordinator.last_outage_cause == expected
    assert coordinator.last_outage_duration is not None


async def test_outage_timestamps_are_recorded(hass) -> None:
    """last_offline_at survives the outage closing, for the diagnostic sensor."""
    gateway = FakeGateway()
    coordinator = _coordinator(hass, gateway)
    gateway.fail_with = TimeoutError("gone")
    with pytest.raises(UpdateFailed):
        await coordinator._async_update_data()

    started = coordinator.offline_since
    assert started is not None
    assert coordinator.last_offline_at == started

    gateway.fail_with = None
    await coordinator._async_update_data()

    assert coordinator.offline_since is None
    assert coordinator.last_offline_at == started, "kept after recovery"
    assert coordinator.outage_count == 1


async def test_first_update_runs_bounded_recovery(hass) -> None:
    """The first poll recovers the link and negotiates the configured target."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_LAST_KNOWN_BAUD: 9600},
        options={CONF_BAUD_RATE: 38400},
    )
    entry.add_to_hass(hass)
    gateway = FakeGateway()
    coordinator = MonopriceCoordinator(hass, gateway, entry)

    data = await coordinator._async_update_data()

    assert gateway.ensure_calls == [38400]
    assert coordinator.active_units == [1]
    assert set(data) == {10, 11, 12, 13, 14, 15, 16}


async def test_expansion_unit_return_is_rediscovered(hass) -> None:
    """An expansion absent at startup can become active without a reload."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_LAST_KNOWN_BAUD: 9600},
        options={CONF_BAUD_RATE: 9600},
    )
    entry.add_to_hass(hass)
    gateway = FakeGateway()
    coordinator = MonopriceCoordinator(hass, gateway, entry)

    await coordinator._async_discover_active_units()
    assert coordinator.active_units == [1]

    gateway.present_units.add(2)
    await coordinator._async_discover_active_units()
    assert coordinator.active_units == [1, 2]
