import { api } from '@/api'
import type { FdState } from '@/types'
import {
  msgForActive,
  run,
  state,
  statusText,
} from '@/composables/sessionShared'

export type MarshalSessionDeps = {
  mutationsEnabled: () => boolean
  isRender: () => boolean
  selectedId: () => string | null
}

export function createMarshalSessionActions(deps: MarshalSessionDeps) {
  function applySnapshot(snap: Partial<FdState> & { type?: string; workspace_id?: string }) {
    if (!msgForActive(snap)) return
    const next: FdState = { ...state.value }
    if (snap.layers) next.layers = snap.layers as FdState['layers']
    if (snap.objects) {
      if (snap.type === 'project_patch' && typeof snap.schema_version !== 'number') {
        next.objects = { ...next.objects, ...(snap.objects as FdState['objects']) }
      } else {
        next.objects = snap.objects as FdState['objects']
      }
    }
    if (snap.selection) {
      const sel = snap.selection
      const prev = next.selection
      if (sel.length !== prev.length || sel.some((id, i) => id !== prev[i])) {
        next.selection = sel
      }
    }
    if (typeof snap.td_connected === 'boolean') next.td_connected = snap.td_connected
    if (snap.slug) next.slug = snap.slug
    if (typeof snap.schema_version === 'number') next.schema_version = snap.schema_version
    state.value = next
  }

  async function setProxyMode(mode: 'mask' | 'mesh') {
    if (!deps.mutationsEnabled()) return
    const id = deps.selectedId()
    if (!id || deps.isRender()) return
    statusText.value = mode === 'mesh' ? 'Cooking mesh proxy…' : 'Proxy: mask'
    await run(() => api.patchObject(id, { proxy_mode: mode }))
  }

  async function refreshSelectedProxy() {
    if (!deps.mutationsEnabled()) return
    const id = deps.selectedId()
    if (!id || deps.isRender()) return
    statusText.value = 'Refreshing proxy…'
    await run(() => api.requestObjectProxies([id]))
  }

  async function refreshMeshProxies() {
    if (!deps.mutationsEnabled() || deps.isRender()) return
    statusText.value = 'Refreshing mesh proxies…'
    await run(() => api.requestObjectProxies())
  }

  async function newProject() {
    if (!deps.mutationsEnabled()) return
    if (deps.isRender()) {
      statusText.value = 'New project clears Marshaled only — switch to Marshaled'
      return
    }
    await run(() => api.clear())
  }

  async function deleteSelected() {
    if (!deps.mutationsEnabled()) return
    if (deps.isRender()) {
      statusText.value = "Can't delete scene operators"
      return
    }
    const ids = [...state.value.selection]
    if (!ids.length) return
    await run(async () => {
      for (const id of ids) {
        await api.deleteObject(id)
      }
    })
  }

  async function deleteObject(id: string) {
    if (!deps.mutationsEnabled()) return
    if (deps.isRender()) {
      statusText.value = "Can't delete scene operators"
      return
    }
    await run(() => api.deleteObject(id))
  }

  return {
    applySnapshot,
    setProxyMode,
    refreshSelectedProxy,
    refreshMeshProxies,
    newProject,
    deleteSelected,
    deleteObject,
  }
}

export type MarshalSessionActions = ReturnType<typeof createMarshalSessionActions>
