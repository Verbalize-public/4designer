import { test, expect } from '@playwright/test'
import { gotoWithWorkspace, seedMarshal } from './helpers'

test('shell shows 4designer brand and outliner', async ({ page, request }) => {
  await seedMarshal(request)
  await gotoWithWorkspace(page)
  await expect(page.getByTestId('fd-brand')).toBeVisible()
  await expect(page.getByText('4designer').first()).toBeVisible()
  await expect(page.getByTestId('fd-outliner')).toBeVisible()
  await expect(page.getByText('Outliner')).toBeVisible()
  // Switch to marshaled to see seeded marshal in outliner
  await page.getByTestId('fd-view-mode').getByText('Marshaled').click()
  await expect(page.getByText('seed_marshal')).toBeVisible({ timeout: 10_000 })
})
