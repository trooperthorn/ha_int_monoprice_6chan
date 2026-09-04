# Design

## Device hierarchy: controller, unit, zone

The integration models the real hardware as a three-level device tree
instead of one flat device per zone: a controller device (the RS-232 link
itself), one unit device per detected physical amplifier (10/20/30), and one
zone device per output (11-16, 21-26, 31-36). Each level links to its parent
through `DeviceInfo["via_device_id"]`.

`via_device_id` must name an already-registered device; it does not accept
an identifier tuple the way the retired `via_device` key did (see
[2026-07-21-device-registry-single-config-entry.md](https://developers.home-assistant.io/blog/2026-07-21-device-registry-single-config-entry)).
Because five platforms (`media_player`, `switch`, `sensor`, `number`,
`remote`) each build entities for the same units, and Home Assistant may set
up those platforms in any order, the integration cannot rely on whichever
platform happens to run first to have already registered the parent device.

The fix is in `device.py::async_ensure_unit_devices`: it registers the
controller device and the given units' devices explicitly, via
`device_registry.async_get_or_create()`, before any entity's `DeviceInfo` is
built. `__init__.py::async_setup_entry` calls it once for the units known
after the coordinator's first refresh, before forwarding to platforms. Each
platform's `_add_units()` calls it again for newly discovered units before
building their entities. The call is idempotent (`async_get_or_create`
returns the existing device when the identifiers already match), so calling
it redundantly across platforms is harmless. `device.py::zone_device_info()`
and `unit_device_info()` then look up the parent's registry id with
`device_registry.async_get_device_id_by_identifier()`, which is guaranteed
to succeed because the parent was registered first.

## Release trigger

A push to `main` (a merged pull request) is the only release trigger. The version is the
one already written in `custom_components/monoprice_custom/manifest.json`; `Release`
validates it through `.release.json`, publishes it, and leaves an already-published version
untouched. `Prepare release` writes the next CalVer into the manifest in a reviewed,
auto-merged PR when release-bearing files changed. `operations.md` has the full path and
`decisions.md` records why tag-resolved versions were abandoned.

The `tests` and `validate` jobs in `release.yml` reuse `test.yml` and `validate.yml`, the
same gate that runs on every pull request, through `workflow_call`, so a release can never
ship on checks weaker than what gated the PR.
