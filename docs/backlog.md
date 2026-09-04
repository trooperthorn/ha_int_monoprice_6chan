# Backlog

- 2026-09-03: `const.py` defines `CONF_NAME`, `MONOPRICE_OBJECT`, and
  `UNDO_UPDATE_LISTENER`, none of which are referenced anywhere in
  `custom_components/` or `tests/`. Confirm they are genuinely unused and
  remove them, or document what still depends on them.
- 2026-09-03: install the release GitHub App on this repository and set
  `RELEASE_AUTOMATION_CLIENT_ID` and `RELEASE_AUTOMATION_PRIVATE_KEY`; until
  then version bumps are manual (see `operations.md`).
- 2026-09-03: the upstream parent repository
  (thebradleysanders/Monoprice-6-Zone-Audio-Controller) has two open PRs worth
  reading for ideas, a config-flow options fix and a pymonoprice reconnect for
  `socket://` bridges; neither applies to this fork's code as written, since
  the coordinator already handles reconnects, but the bridge failure mode they
  describe is worth a test against real hardware.
- 2026-09-03: the tags `v2026.08.13.99`, `v2026.08.20.000`, and `v2026.08.20.01`
  and the upstream `1.2.x` releases predate the CalVer scheme; leave them or
  retire them deliberately, but never reuse the names.
