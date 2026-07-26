import { computed, reactive } from 'vue'
import { api } from '@/api'
import type { FdObject, Trs, ViewMode } from '@/types'
import {
  DELTA_THROTTLE_MS,
  LAYER_COLORS,
  activeWorkspaceId,
  busy,
  daemonOk,
  hasPendingTransform,
  layerFilter,
  markLocalTrs,
  renderState,
  run,
  sessionRuntime,
  started,
  state,
  statusText,
  uiChrome,
  uiHidden,
  viewMode,
  workspaces,
  wsConnected,
} from '@/composables/sessionShared'
import { createWorkspaceActions } from '@/composables/sessionWorkspace'
import { createMarshalSessionActions } from '@/composables/useMarshalSession'
import { createRenderSessionActions } from '@/composables/useRenderSession'

const isRender = computed(() => viewMode.value === 'render')

const objects = computed(() =>
  isRender.value
    ? Object.values(renderState.value.objects)
    : Object.values(state.value.objects),
)

const selectedId = computed(() => {
  const sel = isRender.value ? renderState.value.selection : state.value.selection
  return sel[0] || null
})

const selected = computed<FdObject | null>(() => {
  const id = selectedId.value
  if (!id) return null
  if (isRender.value) return renderState.value.objects[id] || null
  return state.value.objects[id] || null
})

const tdOk = computed(() => {
  const id = activeWorkspaceId.value
  if (!id) return false
  const meta = workspaces.value.find((w) => w.id === id)
  if (meta) return !!meta.connected
  return !!state.value.td_connected
})

const workspaceOffline = computed(() => {
  const id = activeWorkspaceId.value
  if (!id) return true
  const meta = workspaces.value.find((w) => w.id === id)
  return meta ? !meta.connected : !state.value.td_connected
})

const mutationsEnabled = computed(() => !!activeWorkspaceId.value && !workspaceOffline.value)
const objectCount = computed(() => objects.value.length)

const visibleObjects = computed(() =>
  objects.value.filter((o) => {
    if (!o.visible) return false
    const layer = state.value.layers[String(o.layer)]
    if (layer && !layer.visible) return false
    if (layerFilter.value !== 'all' && o.layer !== layerFilter.value) return false
    return true
  }),
)

const renderPath = computed(() => renderState.value.render_path)
const renderTops = computed(() => renderState.value.tops)
const renderStatus = computed(() => renderState.value.status || '')

const render = createRenderSessionActions({
  mutationsEnabled: () => mutationsEnabled.value,
})

const marshal = createMarshalSessionActions({
  mutationsEnabled: () => mutationsEnabled.value,
  isRender: () => isRender.value,
  selectedId: () => selectedId.value,
})

const workspace = createWorkspaceActions({ marshal, render })

function connectWs() {
  if (sessionRuntime.ws) {
    try {
      sessionRuntime.ws.close()
    } catch {
      /* ignore */
    }
    sessionRuntime.ws = null
  }
  const proto = location.protocol === 'https:' ? 'wss' : 'ws'
  sessionRuntime.ws = new WebSocket(`${proto}://${location.host}/ws`)
  sessionRuntime.ws.onopen = () => {
    wsConnected.value = true
    sessionRuntime.ws?.send(JSON.stringify({ type: 'hello', role: 'ui' }))
  }
  sessionRuntime.ws.onclose = () => {
    wsConnected.value = false
    if (sessionRuntime.reconnectTimer != null) window.clearTimeout(sessionRuntime.reconnectTimer)
    sessionRuntime.reconnectTimer = window.setTimeout(connectWs, 1500)
  }
  sessionRuntime.ws.onerror = () => {
    wsConnected.value = false
  }
  sessionRuntime.ws.onmessage = (ev) => {
    try {
      const msg = JSON.parse(String(ev.data))
      if (msg.type === 'workspace_list') {
        workspace.applyWorkspaceList(Array.isArray(msg.workspaces) ? msg.workspaces : [])
        return
      }
      if (msg.type === 'state' || msg.type === 'project_patch') {
        marshal.applySnapshot(msg)
      } else if (msg.type === 'render_state' || msg.type === 'render_patch') {
        render.applyRenderSnapshot(msg)
      }
    } catch {
      /* ignore */
    }
  }
}

async function pollHealth() {
  try {
    const h = await api.health()
    daemonOk.value = h.app === '4designer'
    if (Array.isArray(h.workspaces)) workspace.applyWorkspaceList(h.workspaces)
  } catch {
    daemonOk.value = false
  }
}

function ensureStarted() {
  if (started.value) return
  started.value = true
  void pollHealth()
  connectWs()
  sessionRuntime.healthTimer = window.setInterval(pollHealth, 2000)
  // Cold-load in Render: kick TOP detection once (setViewMode only fires on change).
  if (viewMode.value === 'render') {
    window.setTimeout(() => {
      void render.requestRenderTops()
    }, 300)
  }
  render.syncAutoRefreshLoop()
}

function isUiHidden(id: string): boolean {
  return !!uiHidden[id]
}

function toggleUiHidden(id: string) {
  if (uiHidden[id]) delete uiHidden[id]
  else uiHidden[id] = true
}

function layerColor(layer: number): string {
  const L = state.value.layers[String(layer)]
  if (L?.color) return L.color
  return LAYER_COLORS[layer % LAYER_COLORS.length]
}

function setViewMode(mode: ViewMode) {
  if (viewMode.value === mode) return
  viewMode.value = mode
  uiChrome.setViewMode(mode)
  for (const k of Object.keys(uiHidden)) delete uiHidden[k]
  if (mode === 'marshaled') {
    state.value = { ...state.value, selection: [] }
    void api.setSelection([])
  } else {
    renderState.value = { ...renderState.value, selection: [] }
    void api.setRenderSelection([])
    void render.requestRenderTops()
  }
  render.syncAutoRefreshLoop()
}

function select(id: string | null) {
  if (!mutationsEnabled.value && id) return
  const ids = id ? [id] : []
  const wid = activeWorkspaceId.value
  if (isRender.value) {
    renderState.value = { ...renderState.value, selection: ids }
    if (mutationsEnabled.value) void api.setRenderSelection(ids)
    if (wid) {
      sessionRuntime.ws?.send(JSON.stringify({ type: 'render_select', ids, workspace_id: wid }))
    }
  } else {
    state.value = { ...state.value, selection: ids }
    if (mutationsEnabled.value) void api.setSelection(ids)
    if (wid) sessionRuntime.ws?.send(JSON.stringify({ type: 'select', ids, workspace_id: wid }))
  }
}

function sendTransformDelta(id: string, trs: Trs) {
  if (!mutationsEnabled.value) return
  markLocalTrs(id)
  sessionRuntime.pendingDelta = {
    id,
    trs: { ...trs, t: [...trs.t], r: [...trs.r], s: [...trs.s] },
  }
  if (sessionRuntime.deltaTimer != null) return
  sessionRuntime.deltaTimer = window.setTimeout(() => {
    sessionRuntime.deltaTimer = null
    flushTransformDelta()
  }, DELTA_THROTTLE_MS)
}

function flushTransformDelta() {
  if (sessionRuntime.deltaTimer != null) {
    window.clearTimeout(sessionRuntime.deltaTimer)
    sessionRuntime.deltaTimer = null
  }
  const pending = sessionRuntime.pendingDelta
  sessionRuntime.pendingDelta = null
  if (!pending || !mutationsEnabled.value) return
  const { id, trs } = pending
  const wid = activeWorkspaceId.value
  if (!wid) return
  markLocalTrs(id)
  if (isRender.value) {
    sessionRuntime.ws?.send(
      JSON.stringify({ type: 'render_transform_delta', id, trs, workspace_id: wid }),
    )
  } else {
    sessionRuntime.ws?.send(JSON.stringify({ type: 'transform_delta', id, trs, workspace_id: wid }))
  }
}

async function commitTransform(id: string, trs: Trs) {
  if (!mutationsEnabled.value) return
  markLocalTrs(id)
  flushTransformDelta()
  if (isRender.value) {
    await run(() => api.patchRenderObject(id, trs))
    render.scheduleAutoRefresh(200)
  } else {
    await run(() => api.patchObject(id, { trs }))
  }
}

async function patchSelected(partial: Partial<FdObject> & { trs?: Trs }) {
  if (!mutationsEnabled.value) return
  const id = selectedId.value
  if (!id) return
  if (isRender.value) {
    if (partial.trs) await run(() => api.patchRenderObject(id, partial.trs!))
    return
  }
  await run(() => api.patchObject(id, partial))
}

async function undo() {
  if (!mutationsEnabled.value) return
  if (isRender.value) {
    const snap = await run(() => api.renderUndo())
    if (snap) render.applyRenderSnapshot(snap)
  } else {
    await run(() => api.undo())
  }
}

async function redo() {
  if (!mutationsEnabled.value) return
  if (isRender.value) {
    const snap = await run(() => api.renderRedo())
    if (snap) render.applyRenderSnapshot(snap)
  } else {
    await run(() => api.redo())
  }
}

export function useFourdesignerSession() {
  ensureStarted()
  return reactive({
    state,
    renderState,
    viewMode,
    daemonOk,
    wsConnected,
    tdOk,
    workspaces,
    activeWorkspaceId,
    workspaceOffline,
    mutationsEnabled,
    layerFilter,
    busy,
    statusText,
    objects,
    visibleObjects,
    selectedId,
    selected,
    objectCount,
    renderPath,
    renderTops,
    renderStatus,
    isRender,
    layerColor,
    uiHidden,
    isUiHidden,
    toggleUiHidden,
    setViewMode,
    setWorkspace: workspace.setWorkspace,
    setRenderPath: render.setRenderPath,
    select,
    sendTransformDelta,
    commitTransform,
    hasPendingTransform,
    patchSelected,
    setProxyMode: marshal.setProxyMode,
    refreshSelectedProxy: marshal.refreshSelectedProxy,
    refreshMeshProxies: marshal.refreshMeshProxies,
    undo,
    redo,
    newProject: marshal.newProject,
    deleteSelected: marshal.deleteSelected,
    deleteObject: marshal.deleteObject,
    requestRenderTops: render.requestRenderTops,
    refreshRender: render.refreshRender,
    requestRenderProxies: render.requestRenderProxies,
    scheduleAutoRefresh: render.scheduleAutoRefresh,
    run,
  })
}

export type FourdesignerSession = ReturnType<typeof useFourdesignerSession>
