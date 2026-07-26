import { reactive } from 'vue'
import type { ViewMode } from '@/types'

type ConfirmReq = {
  title: string
  message: string
  danger?: boolean
  resolve: (ok: boolean) => void
}

const FORCE_MASK_KEY = 'fd_force_mask'
const LAYOUT_KEY_V1 = 'fourdesigner.ui.layout.v1'
const LAYOUT_KEY_V2 = 'fourdesigner.ui.layout.v2'
const LAYOUT_KEY = 'fourdesigner.ui.layout.v3'
/** Legacy v2 default preview bottom offset (pre–ViewHelper clearance). */
const LEGACY_PREVIEW_Y = 16

type LayoutPersist = {
  showGrid?: boolean
  outlinerOpen?: boolean
  inspectorOpen?: boolean
  outlinerSize?: number
  inspectorSize?: number
  showGeometry?: boolean
  showLights?: boolean
  previewOpen?: boolean
  previewX?: number
  previewY?: number
  previewW?: number
  previewH?: number
  autoRefresh?: boolean
  autoRefreshIntervalMs?: number
  viewMode?: ViewMode
}

const DEFAULT_OUTLINER_SIZE = 12
const DEFAULT_INSPECTOR_SIZE = 14
const DEFAULT_PREVIEW_X = 16
/** Clear bottom-right ViewHelper (~128px). */
const DEFAULT_PREVIEW_Y = 112
const DEFAULT_PREVIEW_W = 320
const DEFAULT_PREVIEW_H = 180
const DEFAULT_AUTO_REFRESH = true
const DEFAULT_AUTO_REFRESH_MS = 750
const DEFAULT_VIEW_MODE: ViewMode = 'render'

const PREVIEW_MIN_W = 200
const PREVIEW_MIN_H = 120
const PREVIEW_MAX_W_FRAC = 0.6
const PREVIEW_MAX_H_FRAC = 0.8

function clampSize(n: unknown, fallback: number): number {
  const v = typeof n === 'number' ? n : Number(n)
  if (!Number.isFinite(v)) return fallback
  return Math.min(36, Math.max(12, v))
}

function clampPos(n: unknown, fallback: number): number {
  const v = typeof n === 'number' ? n : Number(n)
  if (!Number.isFinite(v)) return fallback
  return Math.max(0, Math.min(4000, Math.round(v)))
}

function clampPreviewDim(
  n: unknown,
  fallback: number,
  min: number,
  max: number,
): number {
  const v = typeof n === 'number' ? n : Number(n)
  if (!Number.isFinite(v)) return fallback
  return Math.round(Math.min(max, Math.max(min, v)))
}

function clampAutoRefreshMs(n: unknown): number {
  const v = typeof n === 'number' ? n : Number(n)
  if (!Number.isFinite(v)) return DEFAULT_AUTO_REFRESH_MS
  return Math.min(5000, Math.max(400, Math.round(v)))
}

function parseViewMode(v: unknown): ViewMode {
  return v === 'marshaled' ? 'marshaled' : 'render'
}

function migrateShowGeometry(parsed: LayoutPersist): boolean {
  if (typeof parsed.showGeometry === 'boolean') return parsed.showGeometry
  // Old Force mask ON meant hide beauty meshes → showGeometry OFF
  try {
    const legacy = localStorage.getItem(FORCE_MASK_KEY)
    if (legacy !== null) {
      localStorage.removeItem(FORCE_MASK_KEY)
      return legacy !== '1'
    }
  } catch {
    /* ignore */
  }
  return true
}

function migrateFromV1(): LayoutPersist | null {
  try {
    const raw = localStorage.getItem(LAYOUT_KEY_V1)
    if (!raw) return null
    const parsed = JSON.parse(raw) as LayoutPersist
    try {
      localStorage.removeItem(LAYOUT_KEY_V1)
    } catch {
      /* ignore */
    }
    return {
      ...parsed,
      outlinerSize: DEFAULT_OUTLINER_SIZE,
      inspectorSize: DEFAULT_INSPECTOR_SIZE,
      previewY: DEFAULT_PREVIEW_Y,
      previewOpen: true,
      autoRefresh: DEFAULT_AUTO_REFRESH,
      viewMode: DEFAULT_VIEW_MODE,
    }
  } catch {
    return null
  }
}

/** v2 → v3: narrower docks + preview above ViewHelper. */
function migrateFromV2(): LayoutPersist | null {
  try {
    const raw = localStorage.getItem(LAYOUT_KEY_V2)
    if (!raw) return null
    const parsed = JSON.parse(raw) as LayoutPersist
    try {
      localStorage.removeItem(LAYOUT_KEY_V2)
    } catch {
      /* ignore */
    }
    const previewY =
      typeof parsed.previewY === 'number' && parsed.previewY === LEGACY_PREVIEW_Y
        ? DEFAULT_PREVIEW_Y
        : parsed.previewY
    return {
      ...parsed,
      outlinerSize: DEFAULT_OUTLINER_SIZE,
      inspectorSize: DEFAULT_INSPECTOR_SIZE,
      previewY,
    }
  } catch {
    return null
  }
}

function defaultLayout(): Required<LayoutPersist> {
  return {
    showGrid: true,
    outlinerOpen: true,
    inspectorOpen: true,
    outlinerSize: DEFAULT_OUTLINER_SIZE,
    inspectorSize: DEFAULT_INSPECTOR_SIZE,
    showGeometry: true,
    showLights: true,
    previewOpen: true,
    previewX: DEFAULT_PREVIEW_X,
    previewY: DEFAULT_PREVIEW_Y,
    previewW: DEFAULT_PREVIEW_W,
    previewH: DEFAULT_PREVIEW_H,
    autoRefresh: DEFAULT_AUTO_REFRESH,
    autoRefreshIntervalMs: DEFAULT_AUTO_REFRESH_MS,
    viewMode: DEFAULT_VIEW_MODE,
  }
}

function loadLayout(): Required<LayoutPersist> {
  const fallback = defaultLayout()
  try {
    const raw = localStorage.getItem(LAYOUT_KEY)
    let parsed: LayoutPersist | null = null
    if (raw) {
      parsed = JSON.parse(raw) as LayoutPersist
    } else {
      parsed = migrateFromV2() ?? migrateFromV1()
      if (!parsed) {
        // Layout missing: still honor legacy force-mask key once
        try {
          const legacy = localStorage.getItem(FORCE_MASK_KEY)
          if (legacy !== null) {
            localStorage.removeItem(FORCE_MASK_KEY)
            fallback.showGeometry = legacy !== '1'
          }
        } catch {
          /* ignore */
        }
        return fallback
      }
    }
    if (!parsed) return fallback
    return {
      showGrid: parsed.showGrid !== false,
      outlinerOpen: parsed.outlinerOpen !== false,
      inspectorOpen: parsed.inspectorOpen !== false,
      outlinerSize: clampSize(parsed.outlinerSize, DEFAULT_OUTLINER_SIZE),
      inspectorSize: clampSize(parsed.inspectorSize, DEFAULT_INSPECTOR_SIZE),
      showGeometry: migrateShowGeometry(parsed),
      showLights: parsed.showLights !== false,
      previewOpen: parsed.previewOpen !== false,
      previewX: clampPos(parsed.previewX, DEFAULT_PREVIEW_X),
      previewY: clampPos(parsed.previewY, DEFAULT_PREVIEW_Y),
      previewW: clampPreviewDim(
        parsed.previewW,
        DEFAULT_PREVIEW_W,
        PREVIEW_MIN_W,
        2400,
      ),
      previewH: clampPreviewDim(
        parsed.previewH,
        DEFAULT_PREVIEW_H,
        PREVIEW_MIN_H,
        1800,
      ),
      autoRefresh: parsed.autoRefresh !== false,
      autoRefreshIntervalMs: clampAutoRefreshMs(parsed.autoRefreshIntervalMs),
      viewMode: parseViewMode(parsed.viewMode),
    }
  } catch {
    return fallback
  }
}

const initial =
  typeof localStorage !== 'undefined' ? loadLayout() : defaultLayout()

const state = reactive<{
  confirm: ConfirmReq | null
  status: string
  settingsOpen: boolean
  showGrid: boolean
  showGeometry: boolean
  showLights: boolean
  outlinerOpen: boolean
  inspectorOpen: boolean
  outlinerSize: number
  inspectorSize: number
  previewOpen: boolean
  previewX: number
  previewY: number
  previewW: number
  previewH: number
  autoRefresh: boolean
  autoRefreshIntervalMs: number
  viewMode: ViewMode
  autoRefreshStatus: 'idle' | 'pending' | 'refreshing'
}>({
  confirm: null,
  status: '',
  settingsOpen: false,
  showGrid: initial.showGrid,
  showGeometry: initial.showGeometry,
  showLights: initial.showLights,
  outlinerOpen: initial.outlinerOpen,
  inspectorOpen: initial.inspectorOpen,
  outlinerSize: initial.outlinerSize,
  inspectorSize: initial.inspectorSize,
  previewOpen: initial.previewOpen,
  previewX: initial.previewX,
  previewY: initial.previewY,
  previewW: initial.previewW,
  previewH: initial.previewH,
  autoRefresh: initial.autoRefresh,
  autoRefreshIntervalMs: initial.autoRefreshIntervalMs,
  viewMode: initial.viewMode,
  autoRefreshStatus: 'idle',
})

function persistLayout() {
  try {
    const payload: LayoutPersist = {
      showGrid: state.showGrid,
      outlinerOpen: state.outlinerOpen,
      inspectorOpen: state.inspectorOpen,
      outlinerSize: state.outlinerSize,
      inspectorSize: state.inspectorSize,
      showGeometry: state.showGeometry,
      showLights: state.showLights,
      previewOpen: state.previewOpen,
      previewX: state.previewX,
      previewY: state.previewY,
      previewW: state.previewW,
      previewH: state.previewH,
      autoRefresh: state.autoRefresh,
      autoRefreshIntervalMs: state.autoRefreshIntervalMs,
      viewMode: state.viewMode,
    }
    localStorage.setItem(LAYOUT_KEY, JSON.stringify(payload))
  } catch {
    /* ignore */
  }
}

export function useUiChrome() {
  function confirmDialog(opts: {
    title: string
    message: string
    danger?: boolean
  }): Promise<boolean> {
    return new Promise((resolve) => {
      state.confirm = { ...opts, resolve }
    })
  }

  function resolveConfirm(ok: boolean) {
    const c = state.confirm
    state.confirm = null
    c?.resolve(ok)
  }

  function setStatus(msg: string) {
    state.status = msg
  }

  function setShowGeometry(on: boolean) {
    state.showGeometry = on
    persistLayout()
  }

  function toggleShowGeometry() {
    setShowGeometry(!state.showGeometry)
  }

  function setShowLights(on: boolean) {
    state.showLights = on
    persistLayout()
  }

  function toggleShowLights() {
    setShowLights(!state.showLights)
  }

  function openSettings() {
    state.settingsOpen = true
  }

  function closeSettings() {
    state.settingsOpen = false
  }

  function setShowGrid(on: boolean) {
    state.showGrid = on
    persistLayout()
  }

  function toggleShowGrid() {
    setShowGrid(!state.showGrid)
  }

  function setOutlinerOpen(on: boolean) {
    state.outlinerOpen = on
    persistLayout()
  }

  function toggleOutliner() {
    setOutlinerOpen(!state.outlinerOpen)
  }

  function setInspectorOpen(on: boolean) {
    state.inspectorOpen = on
    persistLayout()
  }

  function toggleInspector() {
    setInspectorOpen(!state.inspectorOpen)
  }

  function setOutlinerSize(size: number) {
    state.outlinerSize = clampSize(size, DEFAULT_OUTLINER_SIZE)
    persistLayout()
  }

  function setInspectorSize(size: number) {
    state.inspectorSize = clampSize(size, DEFAULT_INSPECTOR_SIZE)
    persistLayout()
  }

  /** Persist sizes from splitpanes resized event (percentages). */
  function applyDockSizes(outlinerPct: number | null, inspectorPct: number | null) {
    if (outlinerPct != null) state.outlinerSize = clampSize(outlinerPct, DEFAULT_OUTLINER_SIZE)
    if (inspectorPct != null) state.inspectorSize = clampSize(inspectorPct, DEFAULT_INSPECTOR_SIZE)
    persistLayout()
  }

  function setPreviewOpen(on: boolean) {
    state.previewOpen = on
    persistLayout()
  }

  function toggleRenderPreview() {
    setPreviewOpen(!state.previewOpen)
  }

  function setPreviewPos(x: number, y: number) {
    state.previewX = clampPos(x, DEFAULT_PREVIEW_X)
    state.previewY = clampPos(y, DEFAULT_PREVIEW_Y)
    persistLayout()
  }

  function previewMaxW(): number {
    if (typeof window === 'undefined') return 2400
    return Math.max(PREVIEW_MIN_W, Math.floor(window.innerWidth * PREVIEW_MAX_W_FRAC))
  }

  function previewMaxH(): number {
    if (typeof window === 'undefined') return 1800
    return Math.max(PREVIEW_MIN_H, Math.floor(window.innerHeight * PREVIEW_MAX_H_FRAC))
  }

  function setPreviewSize(w: number, h: number) {
    state.previewW = clampPreviewDim(w, DEFAULT_PREVIEW_W, PREVIEW_MIN_W, previewMaxW())
    state.previewH = clampPreviewDim(h, DEFAULT_PREVIEW_H, PREVIEW_MIN_H, previewMaxH())
    persistLayout()
  }

  /** Clamp size + pos once and persist once (resize drag path). */
  function setPreviewRect(x: number, y: number, w: number, h: number) {
    state.previewW = clampPreviewDim(w, DEFAULT_PREVIEW_W, PREVIEW_MIN_W, previewMaxW())
    state.previewH = clampPreviewDim(h, DEFAULT_PREVIEW_H, PREVIEW_MIN_H, previewMaxH())
    state.previewX = clampPos(x, DEFAULT_PREVIEW_X)
    state.previewY = clampPos(y, DEFAULT_PREVIEW_Y)
    persistLayout()
  }

  function setAutoRefresh(on: boolean) {
    state.autoRefresh = on
    if (!on) state.autoRefreshStatus = 'idle'
    persistLayout()
  }

  function toggleAutoRefresh() {
    setAutoRefresh(!state.autoRefresh)
  }

  function setAutoRefreshIntervalMs(ms: number) {
    state.autoRefreshIntervalMs = clampAutoRefreshMs(ms)
    persistLayout()
  }

  function setAutoRefreshStatus(s: 'idle' | 'pending' | 'refreshing') {
    state.autoRefreshStatus = s
  }

  function setViewMode(mode: ViewMode) {
    state.viewMode = mode === 'marshaled' ? 'marshaled' : 'render'
    persistLayout()
  }

  return {
    state,
    confirmDialog,
    resolveConfirm,
    setStatus,
    setShowGeometry,
    toggleShowGeometry,
    setShowLights,
    toggleShowLights,
    openSettings,
    closeSettings,
    setShowGrid,
    toggleShowGrid,
    setOutlinerOpen,
    toggleOutliner,
    setInspectorOpen,
    toggleInspector,
    setOutlinerSize,
    setInspectorSize,
    applyDockSizes,
    setPreviewOpen,
    toggleRenderPreview,
    setPreviewPos,
    setPreviewSize,
    setPreviewRect,
    setAutoRefresh,
    toggleAutoRefresh,
    setAutoRefreshIntervalMs,
    setAutoRefreshStatus,
    setViewMode,
    previewMaxW,
    previewMaxH,
    PREVIEW_MIN_W,
    PREVIEW_MIN_H,
  }
}
