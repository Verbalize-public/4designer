import { test, expect } from '@playwright/test'
import { ensureWorkspace, gotoWithWorkspace } from './helpers'

test('connection hero when no workspaces', async ({ page, request }) => {
  // Fresh page without seeding — may still see leftover workspaces from other specs
  // if daemon is reused. Clear by ensuring empty: only assert hero when list empty.
  const health = await request.get('http://127.0.0.1:9983/health')
  const body = await health.json()
  if ((body.workspaces || []).length === 0) {
    await page.goto('/')
    await expect(page.getByTestId('fd-hero')).toBeVisible()
    await expect(page.getByText('Waiting for a TD hub')).toBeVisible()
  } else {
    // With fixture workspace but marshaled empty: switch to marshaled
    await ensureWorkspace(request, 'e2e-empty', 'empty.toe')
    await gotoWithWorkspace(page, 'e2e-empty')
    await page.getByTestId('fd-view-mode').getByText('Marshaled').click()
    await expect(page.getByTestId('fd-hero')).toBeVisible({ timeout: 10_000 })
    await expect(page.getByTestId('fd-hero').getByRole('heading', { name: 'No objects' })).toBeVisible()
  }
})
