"""Coordinator for the Monoprice 6-Zone Amplifier integration."""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime, timedelta
from time import monotonic

import serialx
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from pymonoprice import ZoneStatus

from .api import MonopriceCommandError
from .const import (
    CONF_AUTO_LINK_SPEED,
    CONF_BAUD_RATE,
    CONF_FAILED_BAUD,
    CONF_LAST_KNOWN_BAUD,
    CONF_POLL_INTERVAL,
    CONF_PROVEN_BAUD,
    DEFAULT_AUTO_LINK_SPEED,
    DEFAULT_POLL_INTERVAL,
    MAX_POLL_INTERVAL,
    MIN_POLL_INTERVAL,
)
from .gateway import MonopriceGateway
from .serial import (
    EXPANSION_PROBE_SPACING,
    POWER_ON_BAUD_RATE,
    SUPPORTED_BAUD_RATES,
)

_LOGGER = logging.getLogger(__name__)

DEFAULT_TARGET_BAUD = POWER_ON_BAUD_RATE
UPDATE_INTERVAL = timedelta(seconds=DEFAULT_POLL_INTERVAL)
EXPANSION_DISCOVERY_INTERVAL = timedelta(minutes=5)
# A failed poll runs the six-rate recovery sweep, which costs about two
# seconds per rate, so retrying at the poll interval means the serial line
# is never idle while the amplifier is off. Back off instead: double on each
# consecutive failure up to the cap, and reset on the first success. The
# amplifier is reachable roughly eight seconds after power returns (see
# docs/protocol.md), so the early retries still catch a reboot quickly.
MAX_RETRY_INTERVAL = 120.0

# How an outage ended, inferred from the rate the amplifier was found on.
CAUSE_POWER_CYCLE = "power_cycle"
CAUSE_LINK_FAULT = "link_fault"
CAUSE_UNKNOWN = "unknown"
# A rejection means the reply stream is not where the reader thinks it is,
# so it is handled like a link fault: drop _link_ready and let the next
# poll re-probe rather than parsing onward.
_COMMUNICATION_ERRORS = (
    serialx.SerialException,
    TimeoutError,
    OSError,
    MonopriceCommandError,
)


def poll_interval(entry: ConfigEntry) -> timedelta:
    """Return the configured poll interval, clamped to the supported range."""
    try:
        seconds = int(entry.options.get(CONF_POLL_INTERVAL, DEFAULT_POLL_INTERVAL))
    except (TypeError, ValueError):
        seconds = DEFAULT_POLL_INTERVAL
    return timedelta(seconds=max(MIN_POLL_INTERVAL, min(seconds, MAX_POLL_INTERVAL)))


class MonopriceCoordinator(DataUpdateCoordinator[dict[int, ZoneStatus]]):
    """Manage polling, recovery, and expansion-unit discovery."""

    def __init__(
        self,
        hass: HomeAssistant,
        gateway: MonopriceGateway,
        entry: ConfigEntry,
    ) -> None:
        """Initialize the coordinator."""
        self.gateway = gateway
        self.entry = entry
        self.active_units: list[int] = []
        self.last_successful_poll: datetime | None = None
        self.last_poll_duration: float | None = None
        self._link_ready = False
        self._next_expansion_discovery = 0.0

        # Outage history, for telling a power event apart from a serial fault.
        self.offline_since: datetime | None = None
        self.last_offline_at: datetime | None = None
        self.last_outage_duration: timedelta | None = None
        self.last_outage_cause: str | None = None
        self.outage_count = 0
        self.consecutive_failures = 0
        self.retry_delay: float | None = None
        self._baud_at_outage: int | None = None

        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name="Monoprice 6-Zone",
            update_interval=poll_interval(entry),
        )

    @property
    def auto_link_speed(self) -> bool:
        """Whether the integration works up to the configured rate itself."""
        return bool(
            self.entry.options.get(CONF_AUTO_LINK_SPEED, DEFAULT_AUTO_LINK_SPEED)
        )

    @property
    def target_baud_rate(self) -> int:
        """Return the configured target link speed."""
        configured = self.entry.options.get(CONF_BAUD_RATE, DEFAULT_TARGET_BAUD)
        return (
            int(configured)
            if int(configured) in SUPPORTED_BAUD_RATES
            else DEFAULT_TARGET_BAUD
        )

    async def _async_ensure_link(self) -> None:
        """Run bounded recovery and link-speed negotiation when required."""
        if self._link_ready:
            return
        previous_baud = self.gateway.last_known_baud
        # Seed what the hardware taught us last time, so a rate already proven
        # is returned to directly and one that failed is never retried.
        self.gateway.proven_baud = self.entry.data.get(CONF_PROVEN_BAUD)
        self.gateway.failed_baud = self.entry.data.get(CONF_FAILED_BAUD)

        detected_baud = await self.gateway.async_ensure_link(
            self.target_baud_rate, self.auto_link_speed
        )
        self._link_ready = True
        self._next_expansion_discovery = 0.0

        learned = {
            CONF_LAST_KNOWN_BAUD: detected_baud,
            CONF_PROVEN_BAUD: self.gateway.proven_baud,
            CONF_FAILED_BAUD: self.gateway.failed_baud,
        }
        if detected_baud != previous_baud or any(
            self.entry.data.get(key) != value for key, value in learned.items()
        ):
            self.hass.config_entries.async_update_entry(
                self.entry, data={**self.entry.data, **learned}
            )

    async def _async_discover_active_units(self) -> None:
        """Rediscover expansion units at startup, after recovery, and periodically."""
        active = [1]
        for unit in (2, 3):
            if unit == 3 and 2 not in active:
                break
            # A timeout here means "absent", so give a slow unit room to answer
            # rather than dropping its entities until the next rediscovery.
            await asyncio.sleep(EXPANSION_PROBE_SPACING)
            try:
                status = await self.gateway.async_zone_status(unit * 10 + 1)
            except _COMMUNICATION_ERRORS:
                break
            if status is None:
                break
            active.append(unit)

        if active != self.active_units:
            _LOGGER.info("Detected Monoprice amplifier units: %s", active)
            self.active_units = active
        self._next_expansion_discovery = (
            monotonic() + EXPANSION_DISCOVERY_INTERVAL.total_seconds()
        )

    @property
    def is_online(self) -> bool:
        """Whether the last poll reached the amplifier."""
        return self.offline_since is None and self.last_update_success

    def _next_retry_delay(self) -> float:
        """Return the backoff delay for the next attempt after a failure."""
        base = poll_interval(self.entry).total_seconds()
        delay = base * (2 ** max(0, self.consecutive_failures - 1))
        return min(delay, MAX_RETRY_INTERVAL)

    def _note_failure(self) -> None:
        """Open an outage on the first failure and grow the backoff."""
        self.consecutive_failures += 1
        if self.offline_since is None:
            now = datetime.now(UTC)
            self.offline_since = now
            self.last_offline_at = now
            self.outage_count += 1
            # Captured before recovery negotiates anything, so the comparison
            # on the way back out is against where the link actually was.
            self._baud_at_outage = self.gateway.last_known_baud
            _LOGGER.warning(
                "Monoprice unreachable; outage %d started (link was at %s baud)",
                self.outage_count,
                self._baud_at_outage,
            )
        self.retry_delay = self._next_retry_delay()

    def _classify_outage(self) -> str:
        """Infer whether the amplifier lost power or the serial link dropped.

        The amplifier resets to 9600 whenever it loses power and keeps its
        configured rate otherwise, so a link that was above 9600 and comes back
        at 9600 was power cycled, while one that comes back where it was never
        lost power. Running at 9600 makes the two indistinguishable, which is
        the honest answer rather than a guess.
        """
        before = self._baud_at_outage
        found = self.gateway.last_detected_baud
        if before is None or found is None or before == POWER_ON_BAUD_RATE:
            return CAUSE_UNKNOWN
        if found == POWER_ON_BAUD_RATE:
            return CAUSE_POWER_CYCLE
        if found == before:
            return CAUSE_LINK_FAULT
        return CAUSE_UNKNOWN

    def _note_success(self) -> None:
        """Close any open outage and reset the backoff."""
        self.consecutive_failures = 0
        self.retry_delay = None
        if self.offline_since is None:
            return
        self.last_outage_duration = datetime.now(UTC) - self.offline_since
        self.last_outage_cause = self._classify_outage()
        _LOGGER.info(
            "Monoprice reachable again after %.0fs; suspected cause: %s",
            self.last_outage_duration.total_seconds(),
            self.last_outage_cause,
        )
        self.offline_since = None
        self._baud_at_outage = None

    async def async_refresh_zone(self, zone_id: int) -> None:
        """Refresh one zone and publish it immediately.

        A master id is not a readable zone: `?N0` answers with one frame per
        zone, so querying it here would mis-parse exactly as the poll used to.
        A master write also lands on every zone in the unit, so the whole unit
        is re-read and the first zone mirrored into the master.
        """
        zone_ids = (
            [zone_id + offset for offset in range(1, 7)]
            if zone_id % 10 == 0
            else [zone_id]
        )
        new_data = dict(self.data or {})
        updated = False
        for query_id in zone_ids:
            try:
                status = await self.gateway.async_zone_status(query_id)
            except _COMMUNICATION_ERRORS:
                self._link_ready = False
                await self.async_request_refresh()
                return
            if status is not None:
                new_data[query_id] = status
                updated = True

        if not updated:
            return
        if zone_id % 10 == 0 and (first := new_data.get(zone_id + 1)) is not None:
            new_data[zone_id] = first
        self.async_set_updated_data(new_data)

    async def _async_update_data(self) -> dict[int, ZoneStatus]:
        """Fetch all known zones through the single gateway."""
        started = monotonic()
        try:
            await self._async_ensure_link()
            if monotonic() >= self._next_expansion_discovery:
                await self._async_discover_active_units()

            await self.gateway.async_wake()
            zones: dict[int, ZoneStatus] = {}
            for unit in self.active_units:
                for zone_id in range(unit * 10 + 1, unit * 10 + 7):
                    try:
                        status = await self.gateway.async_zone_status(zone_id)
                    except _COMMUNICATION_ERRORS:
                        if unit == 1:
                            raise
                        _LOGGER.debug(
                            "Expansion unit %d stopped responding during polling", unit
                        )
                        self._next_expansion_discovery = 0.0
                        break
                    if status is not None:
                        zones[zone_id] = status

                # `?N0` is not a unit summary: the amplifier answers it with
                # one status frame per zone (seven EOL sequences), so reading
                # it as a zone parses the first zone's frame and leaves the
                # other five to be read as the answer to the next command.
                # Writes to `<N0..` do broadcast to every zone, so the master
                # entity stays; it mirrors the unit's first zone, which is the
                # state the mis-parse happened to show all along.
                first_zone = zones.get(unit * 10 + 1)
                if first_zone is not None:
                    zones[unit * 10] = first_zone

            self.last_successful_poll = datetime.now(UTC)
            self._note_success()
            return zones
        except _COMMUNICATION_ERRORS as err:
            self._link_ready = False
            self._next_expansion_discovery = 0.0
            self._note_failure()
            _LOGGER.debug(
                "Monoprice communication failed; retrying in %.0fs: %s",
                self.retry_delay,
                err,
            )
            raise UpdateFailed(
                f"Error communicating with amplifier: {err}",
                retry_after=self.retry_delay,
            ) from err
        except Exception as err:
            self._note_failure()
            raise UpdateFailed(
                f"Error communicating with amplifier: {err}",
                retry_after=self.retry_delay,
            ) from err
        finally:
            self.last_poll_duration = monotonic() - started
