import { test, expect } from '@playwright/test'
import {
  BASE,
  DEFAULT_WS,
  gotoWithWorkspace,
  seedMarshal,
  seedRenderScene,
  wsHeaders,
} from './helpers'

test('marshal and render undo stacks are independent', async ({ page, request }) => {
  await seedMarshal(request)
  await seedRenderScene(request)

  await request.patch(`${BASE}/api/objects/e2e-seed`, {
    headers: wsHeaders(DEFAULT_WS),
    data: { trs: { t: [3, 0, 0], r: [0, 0, 0], s: [1, 1, 1] } },
  })
  await request.patch(`${BASE}/api/render/objects/geo-seed`, {
    headers: wsHeaders(DEFAULT_WS),
    data: { trs: { t: [7, 0, 0], r: [0, 0, 0], s: [1, 1, 1] } },
  })

  await request.post(`${BASE}/api/undo`, { headers: wsHeaders(DEFAULT_WS) })
  const marshal = await (await request.get(`${BASE}/api/state`, { headers: wsHeaders(DEFAULT_WS) })).json()
  const render = await (
    await request.get(`${BASE}/api/render/state`, { headers: wsHeaders(DEFAULT_WS) })
  ).json()
  expect(marshal.objects['e2e-seed'].trs.t[0]).toBe(0)
  expect(render.objects['geo-seed'].trs.t[0]).toBe(7)

  await request.post(`${BASE}/api/render/undo`, { headers: wsHeaders(DEFAULT_WS) })
  const render2 = await (
    await request.get(`${BASE}/api/render/state`, { headers: wsHeaders(DEFAULT_WS) })
  ).json()
  expect(render2.objects['geo-seed'].trs.t[0]).toBe(0)

  await gotoWithWorkspace(page)
  await expect(page.getByTestId('fd-brand')).toBeVisible()
})
