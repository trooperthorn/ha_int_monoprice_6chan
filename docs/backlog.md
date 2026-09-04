# Backlog

- 2026-09-03: `const.py` defines `CONF_NAME`, `MONOPRICE_OBJECT`, and
  `UNDO_UPDATE_LISTENER`, none of which are referenced anywhere in
  `custom_components/` or `tests/`. Confirm they are genuinely unused and
  remove them, or document what still depends on them.
- 2026-09-03: install the release GitHub App on this repository and set
  `RELEASE_AUTOMATION_CLIENT_ID` and `RELEASE_AUTOMATION_PRIVATE_KEY`; until
  then version bumps are manual (see `operations.md`).
- 2026-09-03: decide on the two open community PRs (config-flow options fix,
  pymonoprice reconnect on `socket://` bridges); see `decisions.md`.
- 2026-09-03: the tags `v2026.08.13.99`, `v2026.08.20.000`, and `v2026.08.20.01`
  and the upstream `1.2.x` releases predate the CalVer scheme; leave them or
  retire them deliberately, but never reuse the names.
