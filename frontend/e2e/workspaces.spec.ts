import { test, expect } from '@playwright/test'
import { BASE, ensureWorkspace, seedMarshal, wsHeaders } from './helpers'

test('workspace isolation: cross-workspace object 404', async ({ request }) => {
  await seedMarshal(request, { workspaceId: 'ws-a', id: 'obj-a', name: 'only_a' })
  await ensureWorkspace(request, 'ws-b', 'other.toe')

  const miss = await request.get(`${BASE}/api/state`, { headers: wsHeaders('ws-b') })
  expect(miss.ok()).toBeTruthy()
  const body = await miss.json()
  expect(body.objects['obj-a']).toBeUndefined()

  const cross = await request.patch(`${BASE}/api/objects/obj-a`, {
    headers: wsHeaders('ws-b'),
    data: { name: 'hacked' },
  })
  expect(cross.status()).toBe(404)

  const missingHeader = await request.get(`${BASE}/api/state`)
  expect(missingHeader.status()).toBe(400)
})
