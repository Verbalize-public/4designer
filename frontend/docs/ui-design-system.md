# 4designer UI design system

Agent-facing rules for the Vue frontend under `frontend/`.
Follow this when changing chrome, panels, or controls so the UI stays dense and uniform.

## Principles

1. **One AppBar, one canvas toolbar** — never add a third full-width chrome band under the AppBar.
2. **Density over decoration** — control height 24–28px (`--fd-control-h`); AppBar exactly `--fd-appbar-h` (40px).
3. **Work area first** — full-width chrome steals ≤48px vertical (AppBar only). Scene tools float over the viewport.
4. **Tokens only** — no new hardcoded hex/spacing in SFCs; extend `--fd-*` in [`src/styles/tokens.css`](../src/styles/tokens.css). Prefer QA SDK twins for form controls (below).
5. **Mode context in-canvas** — Marshaled vs Render differences appear in the ViewportToolbar (e.g. Render TOP row), not new rails.
6. **Overflow containment** — `html/#app/.fd-shell` never page-scroll; panels use `.fd-panel` / `.fd-scroll` internally.
7. **Side panels are docked** — Outliner/Inspector live in a `splitpanes` dock: resizable, independently toggleable (UI + keymap). Never reintroduce fixed non-resizable columns.

## Prefer QA SDK for form controls

Import from `@quantumaudio/ableton-extension-sdk/vue` (theme already bootstrapped in `main.ts`).

| Use case | Prefer |
|----------|--------|
| Numbers (Inspector TRS, layer) | `QaValueField` / `QaValueFieldGroup` |
| Segmented (view mode, World/Local, Origin/Bounds) | `QaSegmented` |
| Actions (AppBar, dialogs, Render Refresh) | `QaButton` (`variant="ghost"` for quiet row actions) |
| Select lists | `QaSelect` |
| Status LEDs | `QaLed` |
| Modals | `QaDialog` |

**Debounce** Inspector `QaValueField` → `commitTransform` / `patchSelected` (~120ms + flush on pointer-up) so drag ticks do not flood the daemon.

**AppBar height guard:** scope `:deep(.qa-button)` / `:deep(.qa-segmented__item)` to `height: var(--fd-control-h)` inside `.fd-appbar`. Never let stock QA sizing push the bar past 40px.

**Avoid `QaTextInput` in the ViewportToolbar** — it autofocuses on mount and steals shortcut focus. Use native `<input class="qa-input">` for editable path fields (SDK look without autofocus). Do not use `QaTextInput` for readonly Inspector fields either.

### Keep custom (no QA twin / density-specific)

- Transform / Grid tool icons (keymap in tooltip)
- Layer `.chip` filter + eye
- `PanelDockToggle` (header + floating grip)
- `splitpanes` dock + Three canvas host
- Do **not** replace shell with `QaPanel` / `QaToolbar` / `QaStatusBar`

## Chrome model (locked)

```
AppBar (40px)  →  Splitpanes: [Outliner?] | Viewport | [Inspector?]
                                    └─ ViewportToolbar (floating glass)
                                    └─ ViewHelper (bottom-right orientation gizmo; editor OrbitControls only)
                                    └─ RenderPreviewPanel (open by default, edge-resizable, Render mode)
```

| Surface | Owns |
|---------|------|
| **AppBar** (`TopBar.vue`) | Brand, workspace `QaSelect`, `QaSegmented` Marshaled/Render (default **Render**), New/Undo/Redo, Settings gear, status + `QaLed` |
| **ViewportToolbar** (`ViewportToolStrip.vue`) | Transform icons, space/origin segments, Grid, layer chips; **right:** Show geometry + Show lights icons; Render row: **Auto** chip, TOP pick, Refresh (when Auto off), Load meshes, Preview toggle |
| **Outliner / Inspector** | Lists/properties + dock toggle; Inspector TRS/layer via `QaValueField`; Outliner default ≈12%, Inspector ≈14% (max 36%) |
| **ViewHelper** | Three.js orientation gizmo (bottom-right); click axis to reorient plate camera; does not edit TD Camera COMPs |
| **RenderPreviewPanel** | Floating JPEG overlay of the selected Render TOP; edge/corner drag resize; hide/show; no dock; default `previewY` clears ViewHelper |

**Deleted anti-pattern:** full-width `ViewModeRail` / `LayerRail` / `RenderStrip` bands.  
**Dock anti-pattern:** floating undock / dockview without an explicit product pass.  
**Allowed exception:** `RenderPreviewPanel` is a product-pass floating overlay (Render mode only) — not a general undock system.

## Layout persistence

Key: `fourdesigner.ui.layout.v3` (JSON via `useUiChrome`; migrates once from `v2` / `v1`):

- `showGrid`, `showGeometry`, `showLights`, `outlinerOpen`, `inspectorOpen`, `outlinerSize`, `inspectorSize` (%)
- `previewOpen` (default **true**), `previewX`, `previewY` (default **112**), `previewW`, `previewH`
- `autoRefresh` (default **true**), `autoRefreshIntervalMs` (default 750)
- `viewMode` (`marshaled` | `render`, default **render**)

Legacy `fd_force_mask` migrates once into `showGeometry` (inverted) then is removed.  
v2 → v3 forces dock sizes to 12% / 14% and lifts legacy `previewY === 16` to 112 (ViewHelper clearance).

**Show geometry** (icon-only, toolbar right): ON = beauty GLB when available; OFF = AABB/masks.  
**Show lights** (icon-only, toolbar right): ON = keyed fill + Render light icons; OFF = flat ambient, hide light icons.  
**Render preview** (Monitor icon on Render row / `P`): ON = ~2 Hz JPEG poll; OFF = zero preview traffic. Drag borders to resize (Shift = free aspect).  
**Auto-refresh** (Render row chip): debounced scene Refresh (~750ms); never auto Load meshes.

## Keymap chrome defaults

| Action | Default |
|--------|---------|
| `toggleOutliner` | `[` |
| `toggleInspector` | `]` |
| `toggleGrid` | `'` |
| `toggleRenderPreview` | `P` |

Recordable in Settings. Panel dock toggles use icon-only chevrons (header + floating edge); Grid shows a keymap hint on the toolbar button.

## Tokens

Defined in `src/styles/tokens.css`:

| Token | Value | Use |
|-------|-------|-----|
| `--fd-appbar-h` | `40px` | AppBar height |
| `--fd-space-1`…`4` | 4 / 8 / 12 / 16 | Gaps and padding |
| `--fd-radius-sm` / `md` / `pill` | 4 / 6 / 999 | Controls, glass bar, chips |
| `--fd-font-ui` / `micro` | 12px / 10px | Body UI / labels |
| `--fd-control-h` | `26px` | Buttons, inputs, selects + QA height bridge |
| `--fd-panel-w-left` / `right` | 200 / 240 | Legacy size hints (dock uses %) |
| `--fd-glass` | rgba panel | ViewportToolbar background |
| `--fd-accent`, `--fd-panel-*`, `--fd-text`, `--fd-muted`, `--fd-danger` | colors | Keep amber accent system |
| `--fd-layer-0`…`7` | palette | Layer dots |

Also global: `box-sizing: border-box`, `#app { overflow: hidden }`, thin scrollbars on `.fd-panel` / `.fd-scroll`.

Splitter styling: [`styles/dock.css`](../src/styles/dock.css) overrides splitpanes (4px, border/accent — no library blue).

## Component recipes

### Segmented (`QaSegmented`)
View mode in AppBar; World/Local and Origin/Bounds in ViewportToolbar. Compact via `:deep` height bridge.

### Buttons (`QaButton`)
AppBar, dialogs, Render row. Ghost variant for Settings Record/Clear.

### Tool button (ViewportToolbar)
Transform modes + Grid use `QaIconButton` / `QaMdiIcon` (icon-only; keymap in `title`). Space/origin stay `QaSegmented` text.

### Layer chip (`.chip`)
Color dot + index + eye — stay custom.

### Numeric (`QaValueField`)
Inspector TRS (`Vec3Field`) and layer; wide min/max as required by SDK.

### Panel (`.fd-panel` + `.fd-panel-header` + `.fd-panel-body`)
Outliner/Inspector shell inside dock panes.

### Status cluster
AppBar right: ellipsis status + Daemon/TD `QaLed`.

## Layout CSS patterns

```css
.fd-shell { height: 100%; max-height: 100%; overflow: hidden; display: flex; flex-direction: column; }
.fd-main  { flex: 1; min-height: 0; overflow: hidden; }
.fd-dock  { height: 100%; width: 100%; } /* Splitpanes root */
```

ViewportToolbar: `position: absolute; top/left/right: var(--fd-space-2); z-index: 4`. ConnectionHero `z-index: 5` with top padding so copy clears the toolbar.

## Anti-patterns

- Full-width rails under the AppBar
- Duplicate controls (e.g. layer filter in AppBar *and* toolbar)
- Fixed CSS grid columns for Outliner|Viewport|Inspector (use splitpanes)
- `min-height: 100vh` on the shell
- Default thick OS scrollbars / default splitpanes blue theme
- Unbridged large `QaButton` / segmented sizes that break the 40px AppBar
- `QaTextInput` in chrome that autofocuses and steals shortcuts
- Hardcoded `#0e0f12` / `#1a1d24` when a token exists
- Mode-dependent full-width strips that jump layout height

## When adding UI

1. Ask: AppBar (global) or ViewportToolbar (scene/mode)? Never a new band.
2. Prefer a QA twin if one exists; otherwise extend `--fd-*` tokens.
3. Keep Render-only controls inside the toolbar’s second row.
4. Panel visibility goes through `useUiChrome` + keymap when toggleable.
5. Verify: no document scrollbar; dock open/close resizes canvas; AppBar ≤40px; Inspector drag does not lock up the UI.
