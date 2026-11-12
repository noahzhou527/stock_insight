/**
 * Smoke tests (docs/plan-b-draft.md §7 P6): every page opens, search opens a stock, watchlist add / remove.
 * Runs the real backend + built SPA against fake upstreams (backend/tests/e2e_server.py), so no network.
 *   npm run e2e          (builds dist, then runs the tests)
 * Uses the locally installed Edge by default; set PW_CHANNEL=chrome, or PW_CHANNEL=chromium after
 * `npx playwright install chromium`.
 */
import { existsSync } from 'node:fs'
import { join, resolve } from 'node:path'
import { defineConfig, devices } from '@playwright/test'

const root = resolve(import.meta.dirname, '..')
const python = [join(root, '.venv', 'Scripts', 'python.exe'), join(root, '.venv', 'bin', 'python')].find((p) => existsSync(p)) ?? 'python'
const port = Number(process.env.E2E_PORT ?? 8765)
const channel = process.env.PW_CHANNEL ?? 'msedge'

export default defineConfig({
  testDir: './e2e',
  timeout: 30_000,
  expect: { timeout: 10_000 },
  fullyParallel: false, // one shared backend and database
  workers: 1,
  reporter: [['list']],
  use: {
    baseURL: `http://127.0.0.1:${port}`,
    locale: 'zh-CN',
    timezoneId: 'Asia/Shanghai',
    trace: 'retain-on-failure',
  },
  projects: [{ name: 'desktop', use: { ...devices['Desktop Chrome'], viewport: { width: 1440, height: 900 }, ...(channel === 'chromium' ? {} : { channel }) } }],
  webServer: {
    command: `"${python}" -m backend.tests.e2e_server --port ${port}`,
    cwd: root,
    url: `http://127.0.0.1:${port}/api/health`,
    reuseExistingServer: false,
    timeout: 60_000,
  },
})
