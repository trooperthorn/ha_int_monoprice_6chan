"""Zone addressing helpers shared by the platforms that write to the amplifier.

A unit's `N0` address is a broadcast: the amplifier applies the write to all
six of that unit's zones in its own firmware. That is cheap, one command
instead of six, but it is all or nothing. Honouring an exclusion list means
addressing the remaining zones individually, so the decision of which zone ids
a write should reach lives here rather than in each platform.

Deliberately free of Home Assistant imports so the rule can be tested on its
own, without the harness.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

ZONES_PER_UNIT = 6


def is_master(zone_id: int) -> bool:
    """Return whether `zone_id` is a unit's broadcast address."""
    return zone_id % 10 == 0


def unit_zone_ids(zone_id: int) -> list[int]:
    """Return every real zone id belonging to `zone_id`'s unit."""
    unit = zone_id // 10
    return [unit * 10 + offset for offset in range(1, ZONES_PER_UNIT + 1)]


def ignored_zone_ids(raw_values: Iterable[Any] | None) -> set[int]:
    """Return the exclusion list as zone ids, dropping anything unparseable.

    The stored value comes from a config entry, so it may hold strings, ints,
    or leftovers from an older schema; none of those should break a write.
    """
    ignored: set[int] = set()
    for raw in raw_values or ():
        try:
            ignored.add(int(raw))
        except (TypeError, ValueError):
            continue
    return ignored


def write_targets(
    zone_id: int,
    ignored_zones: Iterable[Any] | None = None,
    *,
    honour_exclusions: bool = True,
) -> list[int]:
    """Return the zone ids a write to `zone_id` should actually address.

    A non-master zone is always just itself. A master with nothing excluded
    stays a single broadcast. A master with exclusions expands to the zones
    that remain. `honour_exclusions=False` keeps the broadcast whatever the
    list says, which is what "all off" needs: an excluded zone is one that
    should not be switched on or re-sourced behind the user's back, not one
    that should be left running when everything else is turned off.
    """
    if not is_master(zone_id):
        return [zone_id]
    if not honour_exclusions:
        return [zone_id]
    ignored = ignored_zone_ids(ignored_zones)
    if not ignored:
        return [zone_id]
    return [target for target in unit_zone_ids(zone_id) if target not in ignored]
