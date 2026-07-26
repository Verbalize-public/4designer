import { api, setApiWorkspaceId, type WorkspaceInfo } from '@/api'
import type { MarshalSessionActions } from '@/composables/useMarshalSession'
import type { RenderSessionActions } from '@/composables/useRenderSession'
import {
  WORKSPACE_STORAGE_KEY,
  activeWorkspaceId,
  emptyRenderState,
  emptyState,
  renderState,
  sessionRuntime,
  state,
  uiHidden,
  viewMode,
  workspaces,
} from '@/composables/sessionShared'

export type WorkspaceBootDeps = {
  marshal: Pick<MarshalSessionActions, 'applySnapshot'>
  render: Pick<
    RenderSessionActions,
    'applyRenderSnapshot' | 'requestRenderTops' | 'syncAutoRefreshLoop'
  >
}

export function createWorkspaceActions(deps: WorkspaceBootDeps) {
  function pickDefaultWorkspace(list: WorkspaceInfo[]): string | null {
    if (!list.length) return null
    const connected = list.find((w) => w.connected)
    return (connected || list[0]).id
  }

  function readBootWorkspaceId(): string | null {
    try {
      const q = new URLSearchParams(location.search).get('workspace')
      if (q && q.trim()) return q.trim()
    } catch {
      /* ignore */
    }
    try {
      const stored = localStorage.getItem(WORKSPACE_STORAGE_KEY)
      if (stored && stored.trim()) return stored.trim()
    } catch {
      /* ignore */
    }
    return null
  }

  async function loadWorkspaceState(id: string) {
    setApiWorkspaceId(id)
    activeWorkspaceId.value = id
    try {
      localStorage.setItem(WORKSPACE_STORAGE_KEY, id)
    } catch {
      /* ignore */
    }
    state.value = emptyState()
    renderState.value = emptyRenderState()
    sessionRuntime.lastAppliedPlateFp = ''
    for (const k of Object.keys(uiHidden)) delete uiHidden[k]
    try {
      const snap = await api.state()
      deps.marshal.applySnapshot({ ...snap, type: 'state', workspace_id: id })
    } catch {
      /* offline / empty */
    }
    try {
      const rs = await api.renderState()
      deps.render.applyRenderSnapshot({ ...rs, type: 'render_state', workspace_id: id })
    } catch {
      /* ignore */
    }
    if (viewMode.value === 'render') {
      void deps.render.requestRenderTops()
      deps.render.syncAutoRefreshLoop()
    }
  }

  async function setWorkspace(id: string | null) {
    if (!id) {
      activeWorkspaceId.value = null
      setApiWorkspaceId(null)
      state.value = emptyState()
      renderState.value = emptyRenderState()
      return
    }
    if (id === activeWorkspaceId.value) return
    sessionRuntime.pendingDelta = null
    await loadWorkspaceState(id)
  }

  function applyWorkspaceList(list: WorkspaceInfo[]) {
    workspaces.value = list
    const ids = new Set(list.map((w) => w.id))
    let next = activeWorkspaceId.value
    if (next && !ids.has(next)) next = null
    if (!next) {
      const boot = readBootWorkspaceId()
      if (boot && ids.has(boot)) next = boot
      else next = pickDefaultWorkspace(list)
    }
    if (next && next !== activeWorkspaceId.value) {
      void setWorkspace(next)
    } else if (next) {
      setApiWorkspaceId(next)
      activeWorkspaceId.value = next
      const meta = list.find((w) => w.id === next)
      if (meta && typeof meta.connected === 'boolean') {
        state.value = { ...state.value, td_connected: meta.connected }
      }
    } else if (!list.length) {
      void setWorkspace(null)
    }
  }

  return { setWorkspace, applyWorkspaceList }
}
