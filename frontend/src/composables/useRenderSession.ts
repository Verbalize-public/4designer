import { watch } from 'vue'
import { api } from '@/api'
import type { RenderState } from '@/types'
import {
  anyPendingTransform,
  busy,
  msgForActive,
  renderPlateFingerprint,
  renderState,
  run,
  sessionRuntime,
  statusText,
  uiChrome,
  viewMode,
} from '@/composables/sessionShared'

export type RenderSessionDeps = {
  mutationsEnabled: () => boolean
}

export function createRenderSessionActions(deps: RenderSessionDeps) {
  function applyRenderSnapshot(
    snap: Partial<RenderState> & { type?: string; workspace_id?: string },
  ) {
    if (!msgForActive(snap)) return
    const prev = renderState.value
    const next: RenderState = { ...prev }
    if (typeof snap.render_path === 'string') next.render_path = snap.render_path
    if (snap.tops) next.tops = snap.tops

    let objectsTouched = false
    if (snap.objects) {
      if (snap.type === 'render_patch') {
        next.objects = { ...next.objects, ...(snap.objects as RenderState['objects']) }
        objectsTouched = true
      } else {
        const incoming = snap.objects as RenderState['objects']
        const nextFp = renderPlateFingerprint(incoming, next.render_path)
        const prevFp =
          sessionRuntime.lastAppliedPlateFp ||
          renderPlateFingerprint(prev.objects, prev.render_path)
        // Full scene replace with identical plate → no-op (keep selection + object refs).
        if (nextFp === prevFp && Object.keys(incoming).length === Object.keys(prev.objects).length) {
          if (typeof snap.status === 'string' && snap.status !== prev.status) {
            renderState.value = { ...prev, status: snap.status }
            if (snap.type === 'render_state') statusText.value = snap.status
          }
          return
        }
        next.objects = incoming
        sessionRuntime.lastAppliedPlateFp = nextFp
        objectsTouched = true
      }
    }

    if (snap.selection) {
      const sel = snap.selection
      // Never let a Refresh echo wipe a still-valid local selection.
      if (sel.length === 0 && prev.selection.length > 0) {
        next.selection = prev.selection.filter((id) => id in next.objects)
      } else {
        const cur = next.selection
        if (sel.length !== cur.length || sel.some((id, i) => id !== cur[i])) {
          next.selection = sel
        }
      }
    } else if (objectsTouched && next.selection.length) {
      // Drop selection entries for objects that disappeared.
      next.selection = next.selection.filter((id) => id in next.objects)
    }

    if (typeof snap.status === 'string') next.status = snap.status
    if (snap.counts) next.counts = snap.counts
    if (objectsTouched) {
      sessionRuntime.lastAppliedPlateFp = renderPlateFingerprint(next.objects, next.render_path)
    }
    renderState.value = next
    if (snap.type === 'render_state' && snap.status) {
      statusText.value = snap.status
    }
  }

  /**
   * Debounced auto Refresh (metadata snapshot only — never Load meshes).
   * Skip when Auto is off, a refresh is in flight, or suppress window is active.
   */
  function scheduleAutoRefresh(delayMs?: number) {
    if (!uiChrome.state.autoRefresh) return
    if (viewMode.value !== 'render') return
    if (!deps.mutationsEnabled()) return
    if (sessionRuntime.refreshInFlight || busy.value || anyPendingTransform()) return
    if (performance.now() < sessionRuntime.suppressAutoUntil) return
    const path = renderState.value.render_path.trim()
    if (!path) return
    const delay = delayMs ?? uiChrome.state.autoRefreshIntervalMs
    if (sessionRuntime.autoRefreshTimer != null) window.clearTimeout(sessionRuntime.autoRefreshTimer)
    uiChrome.setAutoRefreshStatus('pending')
    sessionRuntime.autoRefreshTimer = window.setTimeout(() => {
      sessionRuntime.autoRefreshTimer = null
      void runAutoRefresh()
    }, delay)
  }

  async function runAutoRefresh() {
    if (!uiChrome.state.autoRefresh || viewMode.value !== 'render') {
      uiChrome.setAutoRefreshStatus('idle')
      return
    }
    if (sessionRuntime.refreshInFlight || busy.value || anyPendingTransform()) {
      uiChrome.setAutoRefreshStatus('idle')
      return
    }
    const path = renderState.value.render_path.trim()
    if (!path) {
      uiChrome.setAutoRefreshStatus('idle')
      return
    }
    const beforeFp =
      sessionRuntime.lastAppliedPlateFp ||
      renderPlateFingerprint(renderState.value.objects, renderState.value.render_path)
    const beforeSel = [...renderState.value.selection]
    uiChrome.setAutoRefreshStatus('refreshing')
    sessionRuntime.refreshInFlight = true
    // Suppress echo: our refresh → TD PUT scene → WS render_state would re-trigger.
    sessionRuntime.suppressAutoUntil =
      performance.now() + uiChrome.state.autoRefreshIntervalMs + 200
    try {
      await api.refreshRender(path)
      window.setTimeout(() => {
        void api.renderState().then((snap) => {
          const afterFp = renderPlateFingerprint(snap.objects, snap.render_path || path)
          // Identical plate → do not touch UI (selection / Three stays put).
          if (afterFp === beforeFp) {
            // Restore selection if daemon echo cleared it (older daemons).
            if (
              beforeSel.length &&
              (!snap.selection?.length ||
                snap.selection.some((id, i) => id !== beforeSel[i]))
            ) {
              const keep = beforeSel.filter(
                (id) => id in (snap.objects || renderState.value.objects),
              )
              if (keep.length) {
                renderState.value = { ...renderState.value, selection: keep }
                void api.setRenderSelection(keep)
              }
            }
            return
          }
          applyRenderSnapshot({ ...snap, type: 'render_state' })
          if (snap.status) statusText.value = snap.status
        })
      }, 600)
    } catch (e) {
      statusText.value = e instanceof Error ? e.message : String(e)
    } finally {
      sessionRuntime.refreshInFlight = false
      uiChrome.setAutoRefreshStatus('idle')
    }
  }

  function syncAutoRefreshLoop() {
    if (sessionRuntime.autoRefreshLoop != null) {
      window.clearInterval(sessionRuntime.autoRefreshLoop)
      sessionRuntime.autoRefreshLoop = null
    }
    if (!uiChrome.state.autoRefresh || viewMode.value !== 'render') {
      if (sessionRuntime.autoRefreshTimer != null) {
        window.clearTimeout(sessionRuntime.autoRefreshTimer)
        sessionRuntime.autoRefreshTimer = null
      }
      uiChrome.setAutoRefreshStatus('idle')
      return
    }
    // Quiet poll: catches TD-side structural edits that never push without a snapshot kick.
    sessionRuntime.autoRefreshLoop = window.setInterval(() => {
      scheduleAutoRefresh(0)
    }, uiChrome.state.autoRefreshIntervalMs)
  }

  function setRenderPath(path: string) {
    renderState.value = { ...renderState.value, render_path: path }
  }

  async function requestRenderTops() {
    if (!deps.mutationsEnabled()) return
    await run(() => api.requestRenderTops())
    // Poll tops shortly in case WS patch is delayed
    window.setTimeout(() => {
      void api.getRenderTops().then((r) => {
        if (r.tops) applyRenderSnapshot({ tops: r.tops, type: 'render_patch' })
      })
    }, 400)
  }

  async function refreshRender() {
    if (!deps.mutationsEnabled()) return
    const path = renderState.value.render_path.trim()
    if (!path) {
      statusText.value = 'Pick or type a Render TOP path'
      return
    }
    sessionRuntime.refreshInFlight = true
    sessionRuntime.suppressAutoUntil =
      performance.now() + uiChrome.state.autoRefreshIntervalMs + 200
    try {
      await run(() => api.refreshRender(path))
      statusText.value = 'Refreshing…'
      window.setTimeout(() => {
        void api.renderState().then((snap) => {
          applyRenderSnapshot({ ...snap, type: 'render_state' })
          if (snap.status) statusText.value = snap.status
        })
      }, 600)
    } finally {
      sessionRuntime.refreshInFlight = false
    }
  }

  async function requestRenderProxies() {
    if (!deps.mutationsEnabled()) return
    statusText.value = 'Loading mesh proxies…'
    await run(() => api.requestRenderProxies())
    // Poll for uploads (TD cooks sequentially)
    const poll = (n: number) => {
      window.setTimeout(() => {
        void api.renderState().then((snap) => {
          applyRenderSnapshot({ ...snap, type: 'render_state' })
          if (snap.status) statusText.value = snap.status
          if (n > 0 && /Loading|Refreshing/i.test(statusText.value)) {
            /* keep polling while cooking */
          }
          if (n > 0) poll(n - 1)
        })
      }, 800)
    }
    poll(12)
  }

  watch(
    () => [uiChrome.state.autoRefresh, uiChrome.state.autoRefreshIntervalMs] as const,
    () => {
      syncAutoRefreshLoop()
    },
  )

  return {
    applyRenderSnapshot,
    scheduleAutoRefresh,
    syncAutoRefreshLoop,
    setRenderPath,
    requestRenderTops,
    refreshRender,
    requestRenderProxies,
  }
}

export type RenderSessionActions = ReturnType<typeof createRenderSessionActions>
