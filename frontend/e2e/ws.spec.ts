import { test, expect } from '@playwright/test'
import { BASE, DEFAULT_WS, gotoWithWorkspace, seedMarshal, wsHeaders } from './helpers'

test('two UI clients see project_patch after marshal mutate', async ({ browser, request }) => {
  await seedMarshal(request)
  const ctx1 = await browser.newContext()
  const ctx2 = await browser.newContext()
  const page1 = await ctx1.newPage()
  const page2 = await ctx2.newPage()
  await gotoWithWorkspace(page1)
  await gotoWithWorkspace(page2)
  await page1.getByTestId('fd-view-mode').getByText('Marshaled').click()
  await page2.getByTestId('fd-view-mode').getByText('Marshaled').click()
  await expect(page1.getByText('seed_marshal')).toBeVisible({ timeout: 10_000 })
  await expect(page2.getByText('seed_marshal')).toBeVisible({ timeout: 10_000 })

  await request.patch(`${BASE}/api/objects/e2e-seed`, {
    headers: wsHeaders(DEFAULT_WS),
    data: { name: 'seed_renamed' },
  })

  await expect(page1.getByText('seed_renamed')).toBeVisible({ timeout: 10_000 })
  await expect(page2.getByText('seed_renamed')).toBeVisible({ timeout: 10_000 })

  await ctx1.close()
  await ctx2.close()
})
