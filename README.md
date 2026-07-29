# 4designer

Direct-manipulation 3D editing for a TouchDesigner Render TOP — select, move, and rotate scene objects with on-screen gizmos, right inside the network.

<p>
  <img src="https://img.shields.io/badge/version-2.0.0-f0a020?style=flat-square" alt="v2.0.0" />
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
- Pickable proxy icons mark lights and cameras (bulb / cone / distant arrow / camera frustum) for translate and rotate
- In-viewer toolbar — Select / Move / Rotate / Scale, plus Reload and Reset View
- Orientation view-cube in the bottom-right corner — click a face, edge, or corner to snap the edit camera
- Private edit camera — orbit (RMB), pan (MMB), dolly (wheel) without touching your scene camera
- Hover highlighting and per-axis guide lines while dragging
- Idle-cook lock — internal render passes stop cooking when you're not interacting

## Quick start

1. Drag `fourdesigner.tox` into your project.
2. Set its **Render TOP** parameter to the Render TOP driving your scene.
3. Pulse **Open Panel** — the component auto-discovers on load and whenever the Render TOP changes.

## Interaction

| Input | Action |
|-------|--------|
| Toolbar buttons | Switch mode (Select / Move / Rotate / Scale), Reload (Discover), Reset View |
| Orient cube (bottom-right) | Click a face / edge / corner to snap the edit camera |
| LMB click | Select an object, or pick a gizmo handle |
| LMB drag | Translate / scale / rotate the selection |
| RMB drag | Orbit the edit camera |
| MMB drag | Pan the edit camera |
| Wheel | Dolly the edit camera |

## Parameters

| Par | Purpose |
|-----|---------|
| `Rendertop` | The Render TOP whose geometry, lights, and camera are mirrored |
| `Mode` | `select` \| `translate` \| `scale` \| `rotate` |
| `Discover` | Re-scan the Render TOP and rebuild the pick table + proxy icons |
| `Resetview` | Re-seed the edit camera from the scene camera |
| `Openpanel` | Open the component's interactive panel |
| `Status` | Read-only feedback line |

## Limits

- Assumes the selected Object COMP has no Object-COMP parent (transforms are effectively world-space)
- Rotate is exact for Rotate Order `xyz` (TD's default); other orders fall back to an incremental update, flagged in Status
- Scale applies to geometry only — lights and cameras use translate handles in Scale mode
- No multi-select, no snapping, no world/local toggle
- No light intensity/color or camera FOV editing — transform only

## License

MIT — see [LICENSE](LICENSE).
