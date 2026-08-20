"""Tests for config_flow.py's pure helper functions - port-path resolution,
device-path discovery for conflict detection, and source-name parsing -
using the lightweight `homeassistant` stubs (see ha_stubs.py).
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(__file__))
import ha_stubs  # noqa: E402

ha_stubs.install()

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from custom_components.monoprice_custom.config_flow import (  # noqa: E402
    _find_dev_paths,
    _key_for_source,
    _sources_from_config,
)


class TestFindDevPaths(unittest.TestCase):
    def test_finds_paths_in_flat_dict(self):
        data = {"port": "/dev/ttyUSB0", "other": "value"}
        found = _find_dev_paths(data)
        self.assertIn("/dev/ttyUSB0", found)

    def test_finds_paths_nested_in_other_config_entries(self):
        # Mirrors what another integration's config entry might look like -
        # e.g. zwave_js storing its port a level deeper.
        data = {"options": {"usb_path": "/dev/ttyACM0"}, "unrelated": 123}
        found = _find_dev_paths(data)
        self.assertIn("/dev/ttyACM0", found)

    def test_finds_paths_in_lists(self):
        data = {"devices": ["/dev/ttyUSB1", "/dev/ttyUSB2"]}
        found = _find_dev_paths(data)
        self.assertIn("/dev/ttyUSB1", found)
        self.assertIn("/dev/ttyUSB2", found)

    def test_ignores_non_dev_strings(self):
        data = {"name": "Living Room", "count": 6}
        found = _find_dev_paths(data)
        self.assertEqual(found, set())


class TestSourcesFromConfig(unittest.TestCase):
    def test_maps_source_fields_to_numeric_keys(self):
        data = {
            "source_1": "Apple TV",
            "source_2": "  Chromecast  ",
            "source_3": "",  # blank should be dropped
            "source_4": None,  # unset should be dropped
        }
        result = _sources_from_config(data)
        self.assertEqual(result["1"], "Apple TV")
        self.assertEqual(result["2"], "Chromecast")  # stripped
        self.assertNotIn("3", result)
        self.assertNotIn("4", result)

    def test_empty_config_returns_empty_dict(self):
        self.assertEqual(_sources_from_config({}), {})


class TestKeyForSource(unittest.TestCase):
    def test_uses_previous_value_as_suggestion_when_present(self):
        key = _key_for_source(1, "source_1", {"1": "Apple TV"})
        self.assertEqual(key.description, {"suggested_value": "Apple TV"})

    def test_no_suggestion_when_source_not_previously_configured(self):
        key = _key_for_source(2, "source_2", {"1": "Apple TV"})
        self.assertIsNone(key.description)


if __name__ == "__main__":
    unittest.main()
