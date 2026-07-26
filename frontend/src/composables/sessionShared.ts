import { reactive, ref, shallowRef } from 'vue'
import type { WorkspaceInfo } from '@/api'
import { useUiChrome } from '@/composables/useUiChrome'
import type { FdObject, FdState, RenderState, Trs, ViewMode } from '@/types'

export const uiChrome = useUiChrome()

export const LAYER_COLORS = [
  '#4aa3ff',
  '#f0a020',
  '#3ecf8e',
  '#e85d75',
  '#9b7bff',
  '#2ec4b6',
  '#ff6b6b',
  '#c9d1d9',
]

export const WORKSPACE_STORAGE_KEY = 'fourdesigner.activeWorkspace'

export function emptyState(): FdState {
  return {
    schema_version: 1,
    layers: {
      '0': { name: 'Universe 0', visible: true, color: LAYER_COLORS[0] },
    },
    objects: {},
    selection: [],
    td_connected: false,
  }
}

export function emptyRenderState(): RenderState {
  return {
    render_path: '',
    tops: [],
    objects: {},
    selection: [],
    status: '',
    counts: { geo: 0, light: 0, camera: 0 },
  }
}

export function round3(n: unknown): number {
  const v = typeof n === 'number' ? n : Number(n)
  if (!Number.isFinite(v)) return 0
  return Math.round(v * 1e4) / 1e4
}

export function vecKey(v: unknown): string {
  if (!Array.isArray(v)) return '0,0,0'
  return [0, 1, 2].map((i) => round3(v[i])).join(',')
}

/** Structural + TRS/bounds fingerprint — ignore proxy beauty / selection. */
export function renderPlateFingerprint(
  objects: Record<string, FdObject> | undefined,
  renderPath = '',
): string {
  const ids = Object.keys(objects || {}).sort()
  const parts = [renderPath]
  for (const id of ids) {
    const o = objects![id]
    if (!o) continue
    parts.push(
      [
        id,
        o.td_path || '',
        o.kind || '',
        o.name || '',
        o.op_type || '',
        o.light_type || '',
        round3(o.cone_angle ?? 0),
        vecKey(o.trs?.t),
        vecKey(o.trs?.r),
        vecKey(o.trs?.s),
        vecKey(o.bounds?.min),
        vecKey(o.bounds?.max),
      ].join('|'),
    )
  }
  return parts.join('\n')
}

export const state = shallowRef<FdState>(emptyState())
export const renderState = shallowRef<RenderState>(emptyRenderState())
export const viewMode = ref<ViewMode>(uiChrome.state.viewMode)
export const daemonOk = ref(false)
export const wsConnected = ref(false)
export const workspaces = shallowRef<WorkspaceInfo[]>([])
export const activeWorkspaceId = ref<string | null>(null)
export const layerFilter = ref<'all' | number>('all')
export const busy = ref(false)
export const statusText = ref('')
export const started = ref(false)
/** Client-only viewport hide (Outliner eye). Does not patch daemon/TD. */
export const uiHidden = reactive<Record<string, boolean>>({})

/** Mutable runtime bag — lets that need cross-module writes. */
export const sessionRuntime = {
  ws: null as WebSocket | null,
  healthTimer: null as number | null,
  reconnectTimer: null as number | null,
  pendingDelta: null as { id: string; trs: Trs } | null,
  deltaTimer: null as number | null,
  autoRefreshTimer: null as number | null,
  autoRefreshLoop: null as number | null,
  refreshInFlight: false,
  /** Suppress auto-refresh while a local snapshot is settling. */
  suppressAutoUntil: 0,
  lastAppliedPlateFp: '',
  /** Guard window so echo patches don't yank interactive TRS / gizmo pivot. */
  localTrsGuardUntil: new Map<string, number>(),
}

export const DELTA_THROTTLE_MS = 33

export function markLocalTrs(id: string) {
  sessionRuntime.localTrsGuardUntil.set(id, performance.now() + 120)
}

export function hasPendingTransform(id: string) {
  if (sessionRuntime.pendingDelta?.id === id) return true
  const until = sessionRuntime.localTrsGuardUntil.get(id)
  return until != null && performance.now() < until
}

export function anyPendingTransform(): boolean {
  if (sessionRuntime.pendingDelta) return true
  const now = performance.now()
  for (const until of sessionRuntime.localTrsGuardUntil.values()) {
    if (now < until) return true
  }
  return false
}

export function msgForActive(msg: { workspace_id?: string }) {
  const wid = msg.workspace_id
  if (wid == null || wid === '') return true
  return wid === activeWorkspaceId.value
}

export async function run<T>(fn: () => Promise<T>): Promise<T | undefined> {
  busy.value = true
  try {
    return await fn()
  } catch (e) {
    statusText.value = e instanceof Error ? e.message : String(e)
    return undefined
  } finally {
    busy.value = false
  }
}
