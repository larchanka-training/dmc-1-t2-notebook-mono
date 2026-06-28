import { defineConfig, devices } from '@playwright/test'

/**
 * Playwright config for the JS Notebook E2E autotests (issue #157).
 *
 * Targets the LOCAL stack brought up by `./start-services.sh` in the monorepo
 * root (nginx proxy on :80 routing `notebook.com` → Vite, `/api/v1` → FastAPI).
 *
 * Environment overrides:
 *   BASE_URL      — UI origin the browser visits      (default http://notebook.com)
 *   API_BASE_URL  — backend base used for seeding/auth (default http://localhost:8000/api/v1)
 *
 * Allure: results are written to ../allure-results/e2e so they can be merged
 * with the pytest API results under one report (see autotests/scripts/run-all.sh).
 */
const BASE_URL = process.env.BASE_URL ?? 'http://notebook.com'

// The stack serves the UI over plain http://notebook.com (no TLS, custom host) —
// a NON-secure context, where window.crypto.subtle is undefined. The app's boot
// derives the per-user demo-notebook id via uuidV5 (SHA-1 over crypto.subtle),
// which throws and aborts boot before the editor mounts, leaving the notebook
// page stuck on its loading skeleton (title / cells / insert-strip never appear).
// Mark the app origin as secure — as prod is over HTTPS — so crypto.subtle is
// available. See issue #183.
const BASE_ORIGIN = new URL(BASE_URL).origin
const BASE_HOST = new URL(BASE_URL).host

export default defineConfig({
  testDir: '.',
  // auth/notebook/execution/sharing/llm sub-folders hold the specs.
  testMatch: '**/*.spec.ts',
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  // The local dev stack is single-instance (uvicorn --reload, one Vite). Too many
  // parallel workers overwhelm it → transient /auth/me timeouts and navigations.
  // Default to a conservative worker count + retries; override via env.
  retries: Number(process.env.PW_RETRIES ?? (process.env.CI ? 2 : 1)),
  workers: process.env.PW_WORKERS ? Number(process.env.PW_WORKERS) : process.env.CI ? 2 : undefined,
  timeout: 60_000,
  expect: { timeout: 10_000 },
  reporter: [
    ['list'],
    [
      'allure-playwright',
      {
        resultsDir: '../allure-results/e2e',
        detail: true,
        suiteTitle: true,
        environmentInfo: {
          framework: 'Playwright',
          target: BASE_URL,
          node: process.version,
        },
      },
    ],
    ['html', { outputFolder: '../playwright-report', open: 'never' }],
  ],
  use: {
    baseURL: BASE_URL,
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    video: 'retain-on-failure',
    actionTimeout: 15_000,
    navigationTimeout: 20_000,
  },
  projects: [
    {
      name: 'chromium',
      use: {
        ...devices['Desktop Chrome'],
        viewport: { width: 1280, height: 800 },
        // Treat the insecure http app origin as secure so crypto.subtle is
        // defined and boot can derive the demo-notebook id (issue #183).
        launchOptions: {
          args: [`--unsafely-treat-insecure-origin-as-secure=${BASE_ORIGIN}`],
        },
      },
    },
    // Firefox/WebKit are part of the QA matrix (qa/e2e/user-scenarios.md) but
    // Chromium is the PR-blocking smoke browser. Enable the others for the
    // nightly regression run via `--project=firefox`.
    {
      name: 'firefox',
      use: {
        ...devices['Desktop Firefox'],
        viewport: { width: 1280, height: 800 },
        // Firefox equivalent of the chromium secure-origin flag (issue #183).
        launchOptions: {
          firefoxUserPrefs: { 'dom.securecontext.allowlist': BASE_HOST },
        },
      },
    },
  ],
})
