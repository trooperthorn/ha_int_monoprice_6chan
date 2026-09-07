# Decisions

Dated decisions with the alternative rejected and why.

## 2026-09-03, the manifest is the version source, not tag history

`Release` now publishes the version already written in `manifest.json` and refuses drift;
`Prepare release` bumps it through `scripts/set_version.py` in a reviewed PR. Rejected:
resolving the next version from git tags at release time and stamping it only into the
zip. HACS installs this integration from the tagged tree, so that design shipped a tree
whose manifest said one version while the release said another (the tree at
`v2026.09.03.00` carried manifest version 2026.09.01.1).

## 2026-09-03, sequence numbers are unpadded and start at 1

`YYYY.MM.DD.N` with `N` from 1, matching the other trooperthorn repositories and the
shared scripts. Rejected: keeping the two-digit `00` sequence the previous script used.
Older tags keep their names; the reader simply ignores them when counting.

## 2026-09-03, the release archive stays even though HACS installs the tree

The zip is the fixed subject for the SBOM and provenance attestation and is built from
the same tree. Rejected: dropping the archive, which would leave nothing to attest.

## Recorded, devices are modeled controller, unit, zone through `via_device_id`

See `design.md`. Rejected: the retired `via_device` identifier shim, which core removed,
and a flat device per zone, which loses the hardware hierarchy.

## Recorded, entity services register from `async_setup`

All six entity services register through `service.async_register_platform_entity_service`
so they exist before any platform loads (developer blog 2025-09-25). Rejected: the
deprecated per-platform registration.

## 2026-09-08, zone names live only in the config entry, never on the device

`CONF_ZONE_NAMES` stores a zone's room name in the config entry's options, consumed by
`device.py::zone_device_info()`. Rejected: sending it to the amplifier the way source
names and the keypad boot message are sent (`text.py`'s `rename_source`/
`set_keypad_message`). `docs/protocol.md`'s command table has no zone-label command;
the amplifier's own concept of a zone is just its number. There is nothing to reject
here beyond confirming that fact before building anything that assumed otherwise.

## 2026-09-08, this same design already told a live install that removing and
re-adding the integration would break it, and it happened anyway

A production instance's `media_player.monoprice_kitchen`/`garage_left`/`garage_right`
and their bass/treble number entities were lost after the config entry behind them was
removed and a fresh one added, resetting every zone to its default `Zone N` name and
id. The entity ids here are `f"{entry.entry_id}_{zone_id}"` - standard practice, and the
same thing Elk-M1 and Davis Vantage do - so this isn't a defect in that scheme; a
config entry's internal id is only ever stable for that entry's own lifetime, and no
unique-id design survives the entry itself being deleted, because Home Assistant
deletes that entry's entity-registry rows, custom names included, when the entry goes.
The README already said to use Reconfigure instead of removing and re-adding
(added by the 2026-09-06 PR, #9); it did not stop this from happening once, either
because it happened before that line existed or because it was overlooked in the
moment. Rejected: trying to design around this after the fact by keying entity ids to
something that would survive a full delete - Home Assistant does not leave anything to
key against once the entry is gone, so no unique-id scheme fixes a delete-then-recreate.
The actual fix is the zone-names step (this session): naming a zone at setup time, or
from Configure without touching the port at all, means even a future accidental
remove-and-re-add only costs re-typing the same names once, not reverse-engineering
which zone number used to be which room.

## 2026-09-06, `serialx` is now declared in the manifest

The integration has imported `serialx` directly since the serialx migration, but the
manifest listed only `pymonoprice`, so the import worked only because another
integration on the same host (Elk-M1 or Davis) had installed serialx. When those two
failed to install on core 2026.9.1 (their exact `serialx==1.9.0` pins collided with
core's new `serialx==1.10.0` constraint) this integration was one uninstall away from
losing its import. The manifest now declares `serialx>=1.9.0,<2` as a range so core's
own `package_constraints.txt` picks the version; hassfest only requires exact pins for
core integrations. The test pin stays exact and tracks core's current constraint.
