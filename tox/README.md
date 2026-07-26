# 4designer tox

Drop into the user Palette folder (see [docs/RUNBOOK.md](../docs/RUNBOOK.md#palette--discoverability); overview in [../README.md](../README.md)).

Re-exported **2026-07-26** from current `td/` builders (version SoT: [`../VERSION`](../VERSION)):

- `fourdesigner.tox` — hub **1.0.0** (shortcut `fourdesigner`; embeds `hub_lifecycle` / `shm_drain` / `render_snapshot` / `marshal_registry` / `orphan_debounce` + shared `shm_buf`)
- `marshal.tox` — Marshal COMP **1.0.0** (enable Active after place)

Rebuild after VERSION bumps: exec `td/build_hub.py` / `td/build_marshal.py` in TD, then save COMP → tox.
