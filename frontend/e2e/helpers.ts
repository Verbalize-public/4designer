/** Shared Playwright helpers — seed daemon state without TouchDesigner. */

export const BASE = 'http://127.0.0.1:9983'
export const DEFAULT_WS = 'e2e-ws'

export function wsHeaders(workspaceId = DEFAULT_WS) {
  return { 'X-Workspace-Id': workspaceId }
}

export async function ensureWorkspace(
  request: import('@playwright/test').APIRequestContext,
  workspaceId = DEFAULT_WS,
  projectName = 'e2e.toe',
) {
  const r = await request.post(`${BASE}/api/workspaces`, {
    data: {
      id: workspaceId,
      project_name: projectName,
      fixture: true,
      td_connected: true,
    },
  })
  if (!r.ok()) throw new Error(`ensureWorkspace failed: ${r.status()} ${await r.text()}`)
  return r.json()
}

export async function seedMarshal(
  request: import('@playwright/test').APIRequestContext,
  opts: {
    workspaceId?: string
    id?: string
    name?: string
    td_path?: string
    trs?: { t: number[]; r: number[]; s: number[] }
  } = {},
) {
  const workspaceId = opts.workspaceId ?? DEFAULT_WS
  await ensureWorkspace(request, workspaceId)
  const r = await request.post(`${BASE}/api/objects/register`, {
    headers: wsHeaders(workspaceId),
    data: {
      id: opts.id ?? 'e2e-seed',
      name: opts.name ?? 'seed_marshal',
      layer: 0,
      td_path: opts.td_path ?? '/project1/seed',
      trs: opts.trs,
    },
  })
  if (!r.ok()) throw new Error(`seedMarshal failed: ${r.status()} ${await r.text()}`)
  return r.json()
}

export async function seedRenderScene(
  request: import('@playwright/test').APIRequestContext,
  opts: { workspaceId?: string; render_path?: string } = {},
) {
  const workspaceId = opts.workspaceId ?? DEFAULT_WS
  const render_path = opts.render_path ?? '/project1/render1'
  await ensureWorkspace(request, workspaceId)
  const objects = [
    {
      id: 'geo-seed',
      td_path: '/project1/geo1',
      name: 'geo1',
      kind: 'geo',
      trs: { t: [0, 0, 0], r: [0, 0, 0], s: [1, 1, 1] },
      bounds: { min: [-0.5, -0.5, -0.5], max: [0.5, 0.5, 0.5] },
    },
    {
      id: 'light-seed',
      td_path: '/project1/light1',
      name: 'light1',
      kind: 'light',
      light_type: 'point',
      trs: { t: [0, 2, 0], r: [0, 0, 0], s: [1, 1, 1] },
    },
    {
      id: 'cam-seed',
      td_path: '/project1/cam1',
      name: 'cam1',
      kind: 'camera',
    },
  ]
  const r = await request.put(`${BASE}/api/render/scene`, {
    headers: wsHeaders(workspaceId),
    data: { render_path, objects },
  })
  if (!r.ok()) throw new Error(`seedRenderScene failed: ${r.status()} ${await r.text()}`)
  await request.put(`${BASE}/api/render/tops`, {
    headers: wsHeaders(workspaceId),
    data: { tops: [{ path: render_path, name: 'render1' }] },
  })
  return r.json()
}

/** Persist active workspace so the UI selects our fixture on load. */
export async function gotoWithWorkspace(
  page: import('@playwright/test').Page,
  workspaceId = DEFAULT_WS,
) {
  await page.addInitScript((wid) => {
    localStorage.setItem('fourdesigner.activeWorkspace', wid)
    // Prefer Render (default) for most specs; marshaled specs override.
  }, workspaceId)
  await page.goto('/')
}
