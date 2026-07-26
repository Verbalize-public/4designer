/**
 * Capture a live README hero PNG from the running 4designer UI.
 *
 * Prerequisites:
 *   - Daemon serving built UI on http://127.0.0.1:9983
 *   - Prefer Render mode with a workspace connected (optional — UI still captures)
 *
 * Usage (from frontend/):
 *   npx tsx scripts/capture-readme.ts
 *   npm run capture:readme
 *
 * Writes: ../docs/img/fourdesigner-hero.png
 */
import { chromium } from '@playwright/test'
import { mkdirSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const __dirname = dirname(fileURLToPath(import.meta.url))
const outPath = join(__dirname, '..', '..', 'docs', 'img', 'fourdesigner-hero.png')
const baseUrl = process.env.FOURDESIGNER_URL || 'http://127.0.0.1:9983'

async function main() {
  mkdirSync(dirname(outPath), { recursive: true })
  const browser = await chromium.launch({ headless: true })
  const page = await browser.newPage({
    viewport: { width: 1440, height: 900 },
    deviceScaleFactor: 1,
  })
  try {
    await page.goto(baseUrl, { waitUntil: 'networkidle', timeout: 30_000 })
    // Prefer Render mode + open preview for the publication shot
    await page.evaluate(() => {
      try {
        const key = 'fourdesigner.ui.layout.v3'
        const raw = localStorage.getItem(key)
        const layout = raw ? JSON.parse(raw) : {}
        layout.viewMode = 'render'
        layout.previewOpen = true
        layout.autoRefresh = true
        layout.outlinerSize = 12
        layout.inspectorSize = 14
        layout.previewY = 112
        localStorage.setItem(key, JSON.stringify(layout))
      } catch {
        /* ignore */
      }
    })
    await page.reload({ waitUntil: 'networkidle' })
    await page.waitForTimeout(800)
    await page.screenshot({ path: outPath, type: 'png' })
    console.log(`wrote ${outPath}`)
  } finally {
    await browser.close()
  }
}

main().catch((e) => {
  console.error(e)
  process.exit(1)
})
