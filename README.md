# 4designer

Direct-manipulation 3D editing for a TouchDesigner Render TOP — select, move, and rotate scene objects with on-screen gizmos, right inside the network.

<p>
  <img src="https://img.shields.io/badge/version-2.5.0-f0a020?style=flat-square" alt="v2.5.0" />
  <img src="https://img.shields.io/badge/TouchDesigner-2025-f0a020?style=flat-square" alt="TouchDesigner 2025" />
  <img src="https://img.shields.io/badge/license-MIT-f2ebe3?style=flat-square" alt="MIT license" />
</p>

## Why

Moving an object in TouchDesigner usually means hunting parameters in a dialog while the render sits somewhere else on screen. 4designer puts a click-and-drag gizmo directly over your live render: click a geo, light, or camera, drag a handle, and the real Object COMP updates at cook time.

- **One drop-in COMP** — self-contained, no browser tab, no external process.
- **Reads your scene from a Render TOP** — geometry, lights, and camera come straight from its `geometry` / `lights` / `camera` parameters.
- **Native TD geometry gizmos** — analytic CPU ray-picking, no Render Pick DAT.

## Features

- Select, translate, rotate, and scale any Geometry COMP referenced by your Render TOP (scale is geometry-only)
- Selected objects show a yellow AABB outline (visible in Select mode; one cage per object with Ctrl multiselect)
- Local / Global coordinate toggle — gizmo (and nested snap grid) follow the object's own axes or world X/Y/Z
- Ctrl+click to multi-select — the gizmo sits at the selection's center and a drag transforms every selected object at once
- Alt+click cycles through overlapping objects at the click (front→back); Alt+Ctrl+click adds the next overlap to the selection
- Pickable proxy icons mark lights and cameras (bulb / cone / distant arrow / camera frustum) for translate and rotate
- In-viewer icon toolbar — Select / Move / Rotate / Scale, Reload, Reset View, Grid (snap), Local/Global on the left; Render TOP picker + List grouped on the right
- Choose the target Render TOP from the toolbar combobox (scans the parent network); refresh the list from the toolbar or parameters
- Snap-to-grid for translate — per-axis step from parameters; highlighted translate planes show a snap grid when snap is on (grid follows Local or Global axes)
- Orientation view-cube in the bottom-right corner — click a face, edge, or corner to snap the edit camera
- Private edit camera — orbit (RMB), pan (MMB), dolly (wheel) without touching your scene camera
- Hover highlighting and per-axis guide lines while dragging
- Idle-cook lock — internal render passes stop cooking when you're not interacting

## Quick start

1. Drag `fourdesigner.tox` into your project.
2. Set its **Render TOP** parameter (or use the toolbar picker) to the Render TOP driving your scene.
3. Pulse **Open Panel** — the component auto-discovers on load and whenever the Render TOP changes.

## Interaction

| Input | Action |
|-------|--------|
| Toolbar (left) | Switch mode (Select / Move / Rotate / Scale), Reload (Discover), Reset View, Grid (snap toggle), Local/Global |
| Toolbar (right) | Render TOP combobox + List (refresh) — flush grouped strip |
| Orient cube (bottom-right) | Click a face / edge / corner to snap the edit camera |
| LMB click | Select an object (replaces selection), or pick a gizmo handle |
| Ctrl + LMB click | Toggle an object into/out of the selection |
| Alt + LMB click | Cycle through overlapping objects at the click (replace selection) |
| Alt + Ctrl + LMB click | Add the next overlapping object to the current selection |
| LMB drag | Translate / scale / rotate the selection |
| RMB drag | Orbit the edit camera |
| MMB drag | Pan the edit camera |
| Wheel | Dolly the edit camera |

## Parameters

| Par | Purpose |
|-----|---------|
| `Rendertop` | The Render TOP whose geometry, lights, and camera are mirrored |
| `Rendertopchoice` | Menu mirror of `Rendertop` for the toolbar combobox |
| `Refreshrenders` | Re-scan the parent network for Render TOPs and refresh the combobox |
| `Mode` | `select` \| `translate` \| `scale` \| `rotate` |
| `Coordspace` | `local` \| `global` — gizmo / snap-grid orientation |
| `Snapgrid` | Enable translate snap-to-grid |
| `Snapgridx` / `Snapgridy` / `Snapgridz` | Per-axis grid step (default `0.1`) |
| `Discover` | Re-scan the Render TOP and rebuild the pick table + proxy icons |
| `Resetview` | Re-seed the edit camera from the scene camera |
| `Openpanel` | Open the component's interactive panel |
| `Status` | Read-only feedback line |

## Limits

- Translate and rotate respect Object-COMP parenting and all six TD Rotate Orders (`xyz`, `xzy`, `yxz`, `yzx`, `zxy`, `zyx`)
- Scale applies to geometry only — lights and cameras use translate handles in Scale mode
- Multi-select gizmo sits at the AABB-center average; Local orients to the primary (last-selected) object, Global stays world-aligned; scale/rotate still transform each object about its own origin, not the group center
- Snap-to-grid applies to translate only (no rotate/scale snap); when snap is on, a plane grid overlay appears on the highlighted translate plane (no global floor grid) and follows Local/Global
- Render TOP picker lists Render TOPs in the parent network only
- No light intensity/color or camera FOV editing — transform only

## License

MIT — see [LICENSE](LICENSE).
