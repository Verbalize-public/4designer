import { test, expect } from '@playwright/test'
import { DEFAULT_WS, gotoWithWorkspace, seedRenderScene, wsHeaders, BASE } from './helpers'

test('render mode shows scene nodes and preview shell', async ({ page, request }) => {
  await seedRenderScene(request)
  await gotoWithWorkspace(page)
  // Render is default
  await expect(page.getByTestId('fd-view-mode').getByText('Render')).toBeVisible()
  const outliner = page.getByTestId('fd-outliner')
  await expect(outliner.getByText('geo1', { exact: true })).toBeVisible({ timeout: 10_000 })
  await expect(outliner.getByText('light1', { exact: true })).toBeVisible()
  await expect(outliner.getByText('cam1', { exact: true })).toBeVisible()
  await expect(page.getByTestId('fd-render-preview')).toBeVisible()
})

test('render selection survives identical scene refresh (no-op)', async ({ page, request }) => {
  const snap = await seedRenderScene(request)
  await gotoWithWorkspace(page)
  const outliner = page.getByTestId('fd-outliner')
  await expect(outliner.getByText('geo1', { exact: true })).toBeVisible({ timeout: 10_000 })
  await outliner.getByText('geo1', { exact: true }).click()
  // Re-PUT identical scene → daemon no-op; selection should stay
  await request.put(`${BASE}/api/render/scene`, {
    headers: wsHeaders(DEFAULT_WS),
    data: {
      render_path: snap.render_path || '/project1/render1',
      objects: Object.values(snap.objects || {}),
    },
  })
  await page.waitForTimeout(400)
  await expect(outliner.getByText('geo1', { exact: true })).toBeVisible()
})

test('render undo via API updates plate', async ({ page, request }) => {
  await seedRenderScene(request)
  await request.patch(`${BASE}/api/render/objects/geo-seed`, {
    headers: wsHeaders(DEFAULT_WS),
    data: { trs: { t: [2, 0, 0], r: [0, 0, 0], s: [1, 1, 1] } },
  })
  await gotoWithWorkspace(page)
  await expect(page.getByTestId('fd-outliner').getByText('geo1', { exact: true })).toBeVisible({
    timeout: 10_000,
  })
  const undone = await request.post(`${BASE}/api/render/undo`, {
    headers: wsHeaders(DEFAULT_WS),
  })
  expect(undone.ok()).toBeTruthy()
  const state = await request.get(`${BASE}/api/render/state`, {
    headers: wsHeaders(DEFAULT_WS),
  })
  const body = await state.json()
  expect(body.objects['geo-seed'].trs.t[0]).toBe(0)
})
