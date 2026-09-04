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

## 2026-09-03, community pull requests are left for owner review

Two open PRs from outside contributors (config-flow options fix, pymonoprice reconnect on
`socket://` bridges) predate this pass. They were not merged or closed here because the
reconnect change overlaps the coordinator's own error handling and needs the owner's
hardware judgment.

## Recorded, devices are modeled controller, unit, zone through `via_device_id`

See `design.md`. Rejected: the retired `via_device` identifier shim, which core removed,
and a flat device per zone, which loses the hardware hierarchy.

## Recorded, entity services register from `async_setup`

All six entity services register through `service.async_register_platform_entity_service`
so they exist before any platform loads (developer blog 2025-09-25). Rejected: the
deprecated per-platform registration.
