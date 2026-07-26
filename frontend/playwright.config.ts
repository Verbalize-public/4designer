import { defineConfig } from '@playwright/test'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const daemonDir = path.resolve(__dirname, '../daemon')
const python = path.join(daemonDir, '.venv', 'Scripts', 'python.exe')

export default defineConfig({
  testDir: './e2e',
  timeout: 60_000,
  // Single worker: all specs share one daemon process / in-memory SOT.
  workers: 1,
  use: {
    baseURL: 'http://127.0.0.1:9983',
    headless: true,
  },
  webServer: {
    command: `"${python}" -m fourdesigner_daemon`,
    cwd: daemonDir,
    url: 'http://127.0.0.1:9983/health',
    // Opt-in only: a stale daemon on :9983 lacks new routes (e.g. POST /api/workspaces).
    reuseExistingServer: !!process.env.FOURDESIGNER_REUSE,
    timeout: 60_000,
  },
})
