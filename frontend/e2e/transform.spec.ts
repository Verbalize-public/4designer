import { test, expect } from '@playwright/test'
import { BASE, DEFAULT_WS, gotoWithWorkspace, seedMarshal, wsHeaders } from './helpers'

test('marshal TRS patch updates daemon state', async ({ page, request }) => {
  await seedMarshal(request)
  await gotoWithWorkspace(page)
  await page.getByTestId('fd-view-mode').getByText('Marshaled').click()
  await expect(page.getByText('seed_marshal')).toBeVisible({ timeout: 10_000 })

  const patched = await request.patch(`${BASE}/api/objects/e2e-seed`, {
    headers: wsHeaders(DEFAULT_WS),
    data: { trs: { t: [1.5, 0, 0], r: [0, 0, 0], s: [1, 1, 1] } },
  })
  expect(patched.ok()).toBeTruthy()

  const state = await request.get(`${BASE}/api/state`, {
    headers: wsHeaders(DEFAULT_WS),
  })
  const body = await state.json()
  expect(body.objects['e2e-seed'].trs.t[0]).toBeCloseTo(1.5, 3)
  await expect(page.getByText('seed_marshal')).toBeVisible()
})
