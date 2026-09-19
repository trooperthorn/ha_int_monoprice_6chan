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

## 2026-09-19, this integration targets the 10761 six-zone family, and says so

Zone and source counts stay constants. `range(1, 7)` in the coordinator and
every platform, `SOURCE_INDEXES` in `api.py`, and `CONF_SOURCE_1..6` in
`const.py` all encode six, and the same command set runs hardware that is not
six: Monoprice 44519 is four zones, 44518 is eight, Dayton DAX88 is eight zones
and eight sources, Xantech is eight sources. Supporting any of them means zone
count and source count becoming per-entry configuration discovered at setup,
which reaches the config flow, every platform, the entity ids and the stored
options. Rejected: doing that speculatively. The scope is the Monoprice 10761
and the units that match it exactly (DAX66, 39261, WS66i and the generic
clones), and `protocol.md` now marks the zone-id rejection as a fact about
six-zone units rather than a protocol invariant, so the door is documented
rather than nailed shut.

Two nearby families are explicitly out: the Monoprice 31028 / PAM1270 is a
70-volt unit with a different framing entirely (`!` prefix, `+\r` suffix, `ZS`
query suffix, no tone or balance in the status record), and Xantech's own
controllers use single-digit zones, eight sources, a balance range offset by
32, and emit unsolicited keypad updates this reader does not expect. The
family resemblance is real - pyxantech records that Monoprice and Dayton
appear to have licensed or copied the Xantech serial interface - which is
exactly why the boundary needs writing down.

## 2026-09-19, new behaviour options are per-entry, and the exclusion list
changes how a master write is addressed

Poll interval, maximum volume, master power-on volume and the master exclusion
list are all config-entry options rather than constants or YAML. The first
three are clamps and intervals the code applies directly. The exclusion list is
different: `<N0..` broadcasts inside the amplifier's firmware, so excluding a
zone means not using the broadcast at all and addressing the remaining zones
one at a time, six commands instead of one. That trade only happens when a list
is actually set, and `zones.py::write_targets` is the single place that decides
it, kept free of Home Assistant imports so the rule is testable on its own.
Turning everything off deliberately ignores the list, following the openHAB
binding's "except All Off": an excluded zone is one that should not be switched
on or re-sourced behind the user's back, not one that should be left playing
when the house goes quiet.

## 2026-09-19, commands are paced, and the pacing lives in the gateway

Every source that documents timing enforces a floor between RS-232 commands;
pyxantech sets 0.05s on all six series it supports. The gateway's lock
serialized access but let commands run back to back, and the poll issues a
wake plus six to eighteen queries every five seconds. `MIN_COMMAND_INTERVAL`
is now held inside the lock, measured from when the previous command finished.
Rejected: pacing inside `api.py`, which would miss the config-flow path and
would have to be repeated per method; and pacing at the coordinator, which
would leave entity setters and services unpaced.

Expansion-unit probes get their own, larger spacing. A probe that times out is
read as "unit absent" and silently removes six or twelve zones, so the cost of
being early is much higher than the cost of waiting; S1 spaces the equivalent
queries by a full second and `EXPANSION_PROBE_SPACING` matches it. This is a
precaution on precedent rather than a validated fix, because the bench has no
expansion units to reproduce the failure against. Recorded as still open in
`TODO.md` rather than closed.

## 2026-09-18, reply frame counts are per command, confirmed on hardware

A bench session against a 10761 found four commands reading one EOL frame where
the amplifier sends two, and the per-unit poll reading `?N0` as if it were a
zone when it answers with one frame per zone. Each left frames in the buffer for
the next command to read as its own reply, and `send_raw` and `zone_field_status`
returned the command echo rather than the answer. `api.py` now names the count
(`REPLY_EOLS`) where it is known and drains where it is not, and `coordinator.py`
stops querying `?N0` at all. Rejected: draining unconditionally after every
command, which hides a wrong count instead of stating it, and costs a settle
delay on the control writes that are already framed correctly.

The same session found that `VO`/`MU`/`CH`/`TR`/`BS`/`BL` writes are accepted
and discarded while a zone is powered off, and that `<ZZPA01` is accepted and
ignored on this hardware while the malformed `<ZZPA1` draws "Command Error.".
Both are recorded in `protocol.md`. The PA switch now reads the flag back and
raises rather than silently returning to off; rejected: deleting the entity or
moving it to `binary_sensor`, which breaks existing dashboards for a fact
confirmed on one unit only.

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
