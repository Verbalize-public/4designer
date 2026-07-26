import type { FdObject, FdState, RenderState, RenderTopInfo, Trs } from './types'

export type WorkspaceInfo = {
  id: string
  project_name: string
  project_folder: string
  connected: boolean
}

let workspaceId: string | null = null

/** Set by session when active workspace changes; required on all /api/* calls. */
export function setApiWorkspaceId(id: string | null) {
  workspaceId = id && id.trim() ? id.trim() : null
}

export function getApiWorkspaceId(): string | null {
  return workspaceId
}

/** Append workspace query for GLTFLoader / raw URL fetches that cannot set headers. */
export function withWorkspaceQuery(url: string): string {
  const wid = workspaceId
  if (!wid || !url) return url
  if (/[?&]workspace=/.test(url)) return url
  return `${url}${url.includes('?') ? '&' : '?'}workspace=${encodeURIComponent(wid)}`
}

function withWorkspace(init?: RequestInit): RequestInit {
  const headers = new Headers(init?.headers)
  if (workspaceId) headers.set('X-Workspace-Id', workspaceId)
  return { ...init, headers }
}

async function json<T>(res: Response): Promise<T> {
  if (!res.ok) {
    const text = await res.text()
    throw new Error(text || res.statusText)
  }
  return res.json() as Promise<T>
}

function get(path: string) {
  return fetch(path, withWorkspace())
}

function post(path: string, body?: unknown) {
  return fetch(
    path,
    withWorkspace({
      method: 'POST',
      headers: body !== undefined ? { 'Content-Type': 'application/json' } : undefined,
      body: body !== undefined ? JSON.stringify(body) : undefined,
    }),
  )
}

function patch(path: string, body: unknown) {
  return fetch(
    path,
    withWorkspace({
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    }),
  )
}

function del(path: string) {
  return fetch(path, withWorkspace({ method: 'DELETE' }))
}

export const api = {
  health: () =>
    fetch('/health').then((r) =>
      json<{
        app: string
        version: string
        td_connected?: boolean
        workspaces?: WorkspaceInfo[]
      }>(r),
    ),
  workspaces: () =>
    fetch('/api/workspaces').then((r) => json<{ workspaces: WorkspaceInfo[] }>(r)),
  state: () => get('/api/state').then((r) => json<FdState>(r)),
  patchObject: (id: string, body: Partial<FdObject> & { trs?: Trs }) =>
    patch(`/api/objects/${encodeURIComponent(id)}`, body).then((r) => json<FdObject>(r)),
  requestObjectProxies: (ids?: string[]) =>
    post('/api/objects/proxies/request', ids ? { ids } : {}).then((r) =>
      json<{ ok: boolean; count: number }>(r),
    ),
  deleteObject: (id: string) =>
    del(`/api/objects/${encodeURIComponent(id)}?destroy_td=true`).then((r) =>
      json<{ ok: boolean; id: string }>(r),
    ),
  undo: () => post('/api/undo').then((r) => json<FdState & { ok: boolean }>(r)),
  redo: () => post('/api/redo').then((r) => json<FdState & { ok: boolean }>(r)),
  clear: () => post('/api/clear').then((r) => json<FdState>(r)),
  setSelection: (ids: string[]) =>
    post('/api/selection', { ids }).then((r) => json<{ selection: string[] }>(r)),
  patchLayer: (layer: number, body: { name?: string; visible?: boolean }) =>
    patch(`/api/layers/${layer}`, body).then((r) => json(r)),

  renderState: () => get('/api/render/state').then((r) => json<RenderState>(r)),
  requestRenderTops: () =>
    post('/api/render/tops/request').then((r) => json<{ ok: boolean }>(r)),
  refreshRender: (path: string) =>
    post('/api/render/refresh', { path }).then((r) => json<{ ok: boolean; path: string }>(r)),
  patchRenderObject: (id: string, trs: Trs) =>
    patch(`/api/render/objects/${encodeURIComponent(id)}`, { trs }).then((r) =>
      json<FdObject>(r),
    ),
  setRenderSelection: (ids: string[]) =>
    post('/api/render/selection', { ids }).then((r) => json<{ selection: string[] }>(r)),
  renderUndo: () =>
    post('/api/render/undo').then((r) => json<RenderState & { ok: boolean }>(r)),
  renderRedo: () =>
    post('/api/render/redo').then((r) => json<RenderState & { ok: boolean }>(r)),
  getRenderTops: () =>
    get('/api/render/tops').then((r) => json<{ tops: RenderTopInfo[] }>(r)),
  requestRenderProxies: (ids?: string[]) =>
    post('/api/render/proxies/request', ids ? { ids } : {}).then((r) =>
      json<{ ok: boolean }>(r),
    ),
  requestRenderPreview: (path: string) =>
    post('/api/render/preview/request', { path }).then((r) =>
      json<{ ok: boolean; path: string; kicked: boolean; etag?: string; pending?: boolean }>(r),
    ),
  /** Fetch latest preview JPEG. Returns null on 204/304; blob + etag on 200. */
  fetchRenderPreview: async (etag?: string) => {
    const headers: Record<string, string> = {}
    if (etag) headers['If-None-Match'] = `"${etag}"`
    const res = await fetch('/api/render/preview', withWorkspace({ headers }))
    if (res.status === 204 || res.status === 304) {
      return { status: res.status as 204 | 304, blob: null, etag: etag || '' }
    }
    if (!res.ok) {
      const text = await res.text()
      throw new Error(text || res.statusText)
    }
    const rawTag = (res.headers.get('ETag') || '').trim().replace(/^"|"$/g, '')
    const blob = await res.blob()
    return { status: 200 as const, blob, etag: rawTag }
  },
}
