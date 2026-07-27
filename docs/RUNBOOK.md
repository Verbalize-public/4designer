# 4designer — maintainer / agent runbook

> Publication README (hero, quick start, workflows): [`../README.md`](../README.md).
> This file is the deep ops reference for agents and maintainers.

**Wire Stagepad/other POP geometry into a Marshal → see it in a 3D web UI → drag translate → TouchDesigner Out POP moves at cook time, without rebuilding the mesh.**

Sibling tool to Stagepad (no Stagepad API). Port **9983** (never 9982). Health: `{"app":"4designer"}`.

## What changed in v1.0.0

| Change | Detail |
|--------|--------|
| **Version SoT** | Single [`../VERSION`](../VERSION) file (`1.0.0`) shared by daemon, frontend, hub/marshal builders |
| **Render stable / Marshal beta** | Render is the supported default; AppBar labels Marshaled as **beta** |
| **Preview open + resizable** | Render TOP JPEG overlay opens by default; drag window borders to resize (Shift = free aspect) |
| **Auto-refresh** | Toolbar **Auto** chip (on by default) debounces scene Refresh ~750ms; **no-op when plate unchanged** (keeps selection / undo); **Load meshes** stays manual |
| **Shared SHM package** | `shm/` (`fourdesigner-shm`) — single wire-format module for daemon + TD |
| **Local gate** | [`../scripts/check.ps1`](../scripts/check.ps1) — unittest + typecheck + Playwright (no monorepo CI yet) |

## Layout

```
4designer/
  VERSION           Single version SoT (1.0.0)
  scripts/check.ps1 Local release gate
  shm/              Shared SHM package (fourdesigner_shm)
  daemon/           FastAPI SOT + static UI (port 9983)
  frontend/         Vue + Three (OrbitControls + TransformControls)
  frontend/docs/    UI design system for agents (chrome / tokens)
  td/               Hub + Marshal builders / extensions (+ td/ext mixins)
  tox/              Exported .tox for Palette / drag-drop (hub + marshal)
```

UI chrome rules (one AppBar + in-canvas toolbar, tokens, overflow): see [`frontend/docs/ui-design-system.md`](frontend/docs/ui-design-system.md).

## Quick start (M3 e2e)

```text
# terminal — one-time venv
cd daemon
py -3.11 -m venv .venv
.venv\Scripts\pip install -r requirements.txt

# build UI (required once / after UI changes)
cd ../frontend
npm i
npm run build

# run daemon (or pulse Ensure Daemon on the hub in TD)
cd ../daemon
.venv\Scripts\python -m fourdesigner_daemon
```

### TouchDesigner

1. Assert live project is `expe_baseline*.toe`.
2. Drop `tox/fourdesigner.tox` into the network (or exec `td/build_hub.py` → `build_hub()`).
3. Ensure Global OP Shortcut is **`fourdesigner`** (`op.fourdesigner`).
4. On the hub: set **Marshal Name** / **Place In** (optional) → pulse **Create Marshal**.
5. Pulse **Ensure Daemon**, then **Open UI**.
6. Select the marshal in the Outliner → translate → verify Out moves.

### Create a Marshal (preferred order)

| Method | When |
|--------|------|
| Hub pulse **Create Marshal** | Hub already in the project — clones embedded `templates/marshal` (no disk `.py` at pulse time) |
| Palette / drag `tox/marshal.tox` | Discoverability without opening the hub; enable **Active** so it registers |
| `build_marshal.py` | Fallback / CI / rebuilding the embedded template |

Hub parameters (page **4designer**):

| Par | Role |
|-----|------|
| `Createmarshal` | Pulse — spawn a Marshal |
| `Marshalname` | Desired COMP name (auto-suffix `_N` if taken) |
| `Marshalparent` | Place In (OP); empty → hub's parent |
| `Demobox` | Wire a demo `boxPOP` into the new Marshal |
| `Defaultproxymode` | `mask` (default) or `mesh` for new clones |
| `Maxmeshproxies` | Cap concurrent stored GLB proxies (default 4096) |

Status line reports `created /path/...` or a short failure reason (`no template/tox/builder`, bad Place In, etc.).

## Proxy display: mask vs mesh

| Mode | What UI shows | Cost |
|------|---------------|------|
| **mask** (default) | Squared AABB from live `null_rest.bounds()` | Bounds JSON only — scales to many Marshals |
| **mesh** (opt-in) | Decimated GLB (≤4k verts / ≤8k tris) | CPU extract via ephemeral POP to DAT (`pindex`) + upload + GLTF parse |

Marshal pars: `Proxymode`, `Refreshproxy`, `Autoproxy` (default off), `Proxystatus`.

Rules:

- Mask never extracts points, uploads GLB, or fetches `/proxy.glb`.
- Mesh cooks only on **Refresh Proxy** (or Autoproxy+mesh). Never on TRS drag.
- UI **Force mask** toggle draws AABB for everything and skips GLB fetches (panic button).
- Hub rejects mesh proxies past `Maxmeshproxies` with `proxy_cap`.
- Mesh extract uses POP to DAT `extract=vertices` (`pindex` + `prim:vindex`); calling `prims`/`verts` without an attribute name is invalid in TD 2025.

Probe space is **pre-transform** (`null_rest`); UI/TD apply TRS once each.

## View modes: Marshaled | Render

The UI has a **ViewMode** rail (same pill language as layers):

| | **Marshaled** | **Render** |
|---|---------------|------------|
| Source | Live marshal SOT | One-shot snapshot from a Render TOP |
| Plate | Marshals | Geometry + lights (incl. env) + cameras |
| Visuals | AABB / optional GLB | AABB for geo; icons for lights & cameras |
| Transform | `chop_trs` via `set_trs` | Direct Object COMP `tx…sz` |
| Cadence | Live | **Auto** (~750ms debounced Refresh) or manual **Refresh** |
| Pixel preview | — | Floating JPEG overlay (~2 Hz, ≤320px); open by default, edge-resizable; off = zero capture |
| Delete | Destroys Marshal | Disabled |
| Undo | Marshal stack | Separate render undo stack |

**Discovery:** first-level `renderTOP` under `/project1`, plus a manual path field. Hub lists tops on WS connect; UI **Refresh** asks TD to snapshot (`PUT /api/render/scene`). Cold kicks also go on the SHM command ring (HTTP `GET /api/render/pending` remains as fallback when SHM is off).

**Render TOP preview (opt-in):** toolbar Monitor icon or **`P`**. Polls `POST /api/render/preview/request` + `GET /api/render/preview` at ~2 Hz while the panel is open; hub cooks a persistent `preview_res` resolutionTOP and `PUT`s JPEG. Hidden panel stops all kicks (no SHM/HTTP preview traffic). Feedback only — not a realtime render surface.

Render is **out of** the marshal `StateStore` — sibling `RenderStore` + `type: render_state` / `render_patch` WS messages.

**Light icons** use TD `lighttype` (`point` / `cone` / `distant`) + `coneangle` for orientation cues along local **-Z**. Env lights get a hemisphere wire.

**GLB beauty (opt-in):** Refresh stays AABB-only. **Load meshes** cooks capped tip-POP extracts into `/api/render/objects/{id}/proxy.glb` (stale-OK until next Load). Force AABB skips fetches.

## Delete sync (Marshal ↔ plate)

| Action | Result |
|--------|--------|
| Destroy Marshal in TD (or Active off) | Object removed from daemon + UI |
| Delete / Backspace in UI, or Outliner × | Object removed **and** Marshal COMP destroyed |
| Hub WS connect (+ ~2s while connected) | Prunes SOT objects whose `td_path` no longer exists |
| New (clear) | Clears editor state only; TD Marshals stay |

`DELETE /api/objects/{id}?destroy_td=true` enqueues SHM `CMD_DESTROY` + emits WS `destroy_marshal` (and still queues HTTP pending for fallback). The hub drains SHM every frame; when SHM is unavailable it polls `GET /api/pending_destroys` on the rare orphan sweep (~300 frames). Orphans: `POST /api/objects/prune` with `{ids:[...]}`.

Note: TouchDesigner `COMP.destroy()` does not always run Execute DAT `onExit`; mid-session TD deletes are picked up by the hub orphan sweep (and Active-off still unregisters immediately).

## Live transport (SHM)

Hot path between daemon and TD hub uses a named shared-memory buffer (`Local\fourdesigner_v1_{slug}` / `fourdesigner_v1_{slug}`):

| Region | Role |
|--------|------|
| Header + dirty bits | `seq_trs` / `seq_cmd` doorbells |
| 512 × 64 B TRS slots | Live translate/rotate/scale for marshals + render objects |
| 64 × 128 B cmd ring | Destroy, list tops, snapshot, cook proxies, preview JPEG kick |

- Daemon writes dirty slots on `transform_delta` / commit; **does not** WS-`set_trs` to TD when SHM is healthy (UI still gets `project_patch`).
- Hub `DrainShm()` on Execute `framestart` — early-out when seq unchanged; caps 64 slot applies/frame.
- UI throttles transform deltas (~33 ms) and flushes on commit.
- **Large transfers stay HTTP PUT** (snapshot JSON, GLB proxies). SHM staging for multi‑MB blobs is deferred unless PUT profiles as >50% of Refresh/Load wall time.
- Force legacy path: set env `FOURDESIGNER_SHM=0` (daemon + TD) — WS `set_trs` + rare HTTP pending polls.

`/health` reports `shm_ok` / `shm_name`.

### MCP verify (M3)

1. `get_td_node_errors` on hub (`op.fourdesigner`) and marshal — clean.
2. Pulse `Createmarshal` → new marshal under Place In / hub parent; Active → `Status=registered` when daemon is up.
3. `PATCH http://127.0.0.1:9983/api/objects/{id}` with `{"trs":{"t":[1,0,0],"r":[0,0,0],"s":[1,1,1]}}`.
4. Read marshal `chop_trs` → `tx == 1` (±1e-3).
5. Optional: Render TOP of Marshal Out — image must change; black = fail.

## Multi-TD workspaces

One daemon on **:9983** serves every TouchDesigner instance:

| Piece | Behavior |
|-------|----------|
| Workspace | One hub WS session; id on hub par `Workspaceid` (UUID) |
| Isolation | Per-workspace SOT, render store, SHM (`fourdesigner_v1_w_{id}`) |
| HTTP | All `/api/*` require header `X-Workspace-Id` |
| Hello | TD sends `workspace_id` + `project.name` / `project.folder` |
| Rekey | Second live hub with the same id gets `workspace_rekey` |
| Daemon singleton | Bind-or-exit — second process exits 0 if port taken |
| UI | AppBar workspace `QaSelect` (above Marshaled\|Render); offline disables edits |

`GET /health` and `GET /api/workspaces` list connected hubs. Persistence of editor JSON across daemon restarts is **not** in v1 — marshals re-register on reconnect.

## Hub discovery (portable)

| Tool | Global OP Shortcut | Resolve from clients |
|------|--------------------|----------------------|
| 4designer hub | `fourdesigner` | `op.fourdesigner` |
| Stagepad (later) | `stagepad` | `op.stagepad` |

> TD Global OP Shortcuts must be valid Python identifiers — a leading digit
> (`4designer`) is rejected. Product name stays **4designer**; discovery is
> `op.fourdesigner`.

Marshals resolve hub with:

```python
hub = getattr(op, 'fourdesigner', None)
if hub is None and self.par.Hub:
    hub = op(self.par.Hub)
```

No absolute `/project1/...` inside shippable COMPs. Builders may place nodes under `/project1` in this repo only.

## Daemon Dir

Hub par `Daemondir` defaults to the repository's absolute `daemon/` path when the hub is built. Create the venv there once so Ensure can spawn detached. A previously exported `.tox` may retain its old value; rebuild the hub or set `Daemondir` to this clone's `daemon/`.

## Euler / coords

SOT and Marshal use **XYZ degrees**, Y-up (TD Geo default). UI uses the same via `trs.ts`.

## Viewport tools

| Control | Default shortcut | Behavior |
|---------|------------------|----------|
| Grab | `G` | Click-drag on camera plane (Blender Move) |
| Rotate | `R` | TransformControls rotate |
| Scale | `S` | TransformControls scale |
| Translate gizmo | `T` | Axis gizmo translate (4designer extension) |
| Undo / Redo | `Ctrl+Z` / `Ctrl+Shift+Z` | Daemon undo stack |
| Delete | `X` or `Delete` | Destroy selected Marshal + plate object |
| Space / Pivot | unbound | World/Local, Origin/Bounds — bind in Settings |

Shortcuts are configurable under **Settings** (TopBar); stored in `localStorage` (`fourdesigner.keymap.v1`). Reset restores Blender defaults.

`trs` sent to TD always stays the Marshal/transformPOP origin — Bounds only offsets the UI pivot.

## Palette / discoverability

**Shipped path (works now):** export `.tox` into `tox/` and install into the user Palette.

1. After a clean `build_hub()` / Create Marshal (or `build_marshal(active=True)`), save:
   - Hub → `tox/fourdesigner.tox`
   - Marshal → `tox/marshal.tox`
2. Copy both into your user Palette folder (TD: `app.userPaletteFolder`, typically
   `Documents/Derivative/Palette/`) under a subfolder, e.g. `Palette/4designer/`.
3. Open the Palette browser → **4designer** → drag **fourdesigner** / **marshal** into a network.
4. On hub import: confirm shortcut **`fourdesigner`**. On marshal import: leave **Hub** empty (uses `op.fourdesigner`) and **Active** on.

Re-export tox after substantive hub/marshal changes (`About` version bump).

### TDFam (optional / deferred)

A full OP Create (TAB) family is **not** packaged yet. When adding TDFam integration:

1. Drop `TDFam_create.tox` into the project.
2. Point **Opfolder** at this repository's `tox/` directory (or embed COMPs under Opcomp).
3. **Ensure Manifests** → toggle **Install**.

Until then, use hub **Create Marshal** + Palette tox.

## Tox export (maintainers)

```text
# In TD / MCP after builders succeed:
op.fourdesigner.save(str(_module_dir().parent / 'tox' / 'fourdesigner.tox'), createFolders=True)
# Fresh active marshal for Palette (not the dormant templates/marshal):
# build_marshal(name='_tox_marshal', active=True) → save → destroy
```

On import elsewhere: Global OP Shortcut **`fourdesigner`** once per project; set hub `Daemondir` to this clone's `daemon/` directory.

## M3 e2e checklist

- [ ] `GET :9983/health` → `app=4designer`
- [ ] Hub present (`op.fourdesigner`) + **Create Marshal** → errors clean
- [ ] Active Marshal → object in `GET /api/state` with `td_path`
- [ ] UI Outliner shows name; Daemon+TD LEDs green
- [ ] `PATCH /api/objects/{id}` `trs.t=[1,0,0]` → marshal `chop_trs` tx≈1; Out bounds center ≠ identity
- [ ] Point count unchanged before/after TRS
- [ ] Idle hub: no Timer CHOPs / per-frame Python

## Tests

Preferred local gate (version check + all suites):

```text
pwsh scripts/check.ps1
```

Python (daemon):

```text
cd daemon
.venv\Scripts\pip install -r requirements.txt   # includes -e ../shm
.venv\Scripts\python -m unittest discover -s . -p "test_*.py" -q
```

Modules: `test_state`, `test_proxy_store`, `test_render_store`, `test_workspaces`,
`test_delete_prune`, `test_shm_buf`, `test_shm_wire`, `test_v1_stability`,
`test_orphan_debounce`.

SHM parity:

```text
cd shm
../daemon/.venv/Scripts/python -m unittest discover -s tests -p "test_*.py" -q
```

Frontend e2e (daemon+UI only — **no live TD**). Specs seed via `POST /api/workspaces`
with `fixture: true` and `PUT /api/render/scene`:

```text
cd frontend
npm run typecheck
npm run test:e2e
```

Specs: `smoke`, `render`, `transform`, `ws`, `workspaces`, `undo`, `empty`.

## Media (README assets)

| Asset | Regen |
|-------|-------|
| `docs/demo.mp4` | `ffmpeg -i <raw>.mp4 -an -vf "scale=1280:-2:flags=lanczos" -c:v libx264 -preset slow -crf 27 -pix_fmt yuv420p -movflags +faststart docs/demo.mp4` |
| `docs/img/demo.gif` (README hero, loops) | `ffmpeg -i <raw>.mp4 -vf "fps=12,scale=900:-1:flags=lanczos,split[s0][s1];[s0]palettegen=max_colors=128[p];[s1][p]paletteuse=dither=bayer:bayer_scale=3" -loop 0 docs/img/demo.gif` |
| Live UI still | `cd frontend && npm run capture:readme` (daemon must be up) → `docs/img/fourdesigner-hero.png` |

Keep both demo files under ~1 MB each so clones stay light.

## Deferred (out of v1.0.0)

- Daemon-restart persistence (marshals re-register on reconnect)
- Live-TD e2e automation (lab target) / monorepo CI wiring
- SHM multi-MB blob staging (large payloads stay HTTP PUT)
- TDFam TAB discovery
- Render realtime scene streaming, FOV/lens editing, destroying scene OPs, multi-Render TOP union

## Non-goals (v1)

- Full TDFam family packaging (tox + Palette first; TDFam optional later)
- 100-instance automated FPS gate
- ShortcutOverlay
- Live full-res mesh streaming / materials / UVs
- Stagepad deep integration / animation / multi-select
- Render view: realtime scene streaming (low-rate JPEG preview overlay is allowed), FOV/lens editing, destroying scene OPs, multi-Render TOP union

## Perf note

TRS is CHOP-driven into `transformPOP`. Default **mask** mode never runs the GLB bridge. Idle hub does not run per-frame Python. Mesh proxies are capped (`Maxmeshproxies`).
