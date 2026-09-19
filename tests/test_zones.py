"""Which zone ids a write actually reaches.

`<N0..` broadcasts inside the amplifier's firmware, so an exclusion list can
only be honoured by addressing the remaining zones one at a time. These tests
pin the rule, including the deliberate exemption for turning everything off.
"""

import importlib
import sys
import unittest
from pathlib import Path
from types import ModuleType

PACKAGE_ROOT = Path(__file__).parents[1] / "custom_components" / "monoprice_custom"
package = sys.modules.setdefault("monoprice_custom", ModuleType("monoprice_custom"))
package.__path__ = [str(PACKAGE_ROOT)]

zones = importlib.import_module("monoprice_custom.zones")


class TestWriteTargets(unittest.TestCase):
    def test_a_real_zone_is_always_just_itself(self):
        self.assertEqual(zones.write_targets(13), [13])
        self.assertEqual(zones.write_targets(13, ["13", "14"]), [13])

    def test_master_with_no_exclusions_stays_one_broadcast(self):
        # Six commands replaced by one, which is the whole point of `<N0..`.
        self.assertEqual(zones.write_targets(10), [10])
        self.assertEqual(zones.write_targets(10, []), [10])

    def test_master_with_exclusions_expands_to_the_rest(self):
        self.assertEqual(
            zones.write_targets(10, ["12", "15"]),
            [11, 13, 14, 16],
        )

    def test_exclusions_are_scoped_to_their_own_unit(self):
        self.assertEqual(
            zones.write_targets(20, ["22"]),
            [21, 23, 24, 25, 26],
        )
        # A unit-2 exclusion must not silently expand unit 1's broadcast.
        self.assertEqual(zones.write_targets(10, ["22"]), [11, 12, 13, 14, 15, 16])

    def test_all_off_ignores_the_exclusion_list(self):
        # An excluded zone is one that should not be switched on or re-sourced,
        # not one that should be left playing when everything else goes off.
        self.assertEqual(
            zones.write_targets(10, ["12"], honour_exclusions=False),
            [10],
        )

    def test_every_zone_excluded_sends_nothing(self):
        self.assertEqual(
            zones.write_targets(10, [str(z) for z in range(11, 17)]),
            [],
        )

    def test_unparseable_entries_are_ignored_not_fatal(self):
        self.assertEqual(
            zones.write_targets(10, ["12", None, "", "abc"]),
            [11, 13, 14, 15, 16],
        )

    def test_integer_and_string_entries_both_work(self):
        self.assertEqual(
            zones.write_targets(10, [12, "15"]),
            [11, 13, 14, 16],
        )

    def test_missing_option_is_treated_as_no_exclusions(self):
        self.assertEqual(zones.write_targets(10, None), [10])


class TestZoneIdentity(unittest.TestCase):
    def test_master_ids(self):
        for zone_id in (10, 20, 30):
            self.assertTrue(zones.is_master(zone_id))
        for zone_id in (11, 16, 21, 36):
            self.assertFalse(zones.is_master(zone_id))

    def test_unit_zone_ids(self):
        self.assertEqual(zones.unit_zone_ids(10), [11, 12, 13, 14, 15, 16])
        self.assertEqual(zones.unit_zone_ids(30), [31, 32, 33, 34, 35, 36])
        # Derived from the unit, so a real zone id gives its own unit's list.
        self.assertEqual(zones.unit_zone_ids(23), [21, 22, 23, 24, 25, 26])


if __name__ == "__main__":
    unittest.main()
