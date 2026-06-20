import { test as base, expect, type APIRequestContext, type Page } from '@playwright/test'
import * as allure from 'allure-js-commons'

/** Attach a labelled JSON/text payload to the Allure report (best-effort). */
async function attach(name: string, content: unknown): Promise<void> {
  try {
    const body = typeof content === 'string' ? content : JSON.stringify(content, null, 2)
    await allure.attachment(name, body, 'application/json')
  } catch {
    /* report is best-effort — never fail a test on attachment issues */
  }
}

/**
 * Shared fixtures and helpers (AT-INFRA-01).
 *
 * Auth model (verified against api@8439b84 / ui@0082a09):
 *  - POST /auth/otp/request  → in a local-like backend (APP_ENV=dev/local/test)
 *    the response body is { otp, expiresAt }. We use that to drive a real,
 *    end-to-end OTP login without any email inbox.
 *  - POST /auth/otp/verify   → { accessToken, refreshToken, user }.
 *  - The UI persists the session in localStorage under the keys
 *    `session.accessToken`, `session.refreshToken`, `session.user`
 *    (JSON-encoded, see ui/src/entities/session/model/session.ts).
 */

export const API_BASE_URL = process.env.API_BASE_URL ?? 'http://localhost:8000/api/v1'

/**
 * Settle wait after a mutating API call. The dev backend commits in its request
 * teardown, which races sending the response, so a machine-speed follow-up can
 * miss the write (a human never does). 1s closes the window. See the API
 * suite's conftest for the same mechanism.
 */
export const SETTLE_MS = Number(process.env.SETTLE_MS ?? '1000')
const settle = () => new Promise((r) => setTimeout(r, SETTLE_MS))

export interface SessionUser {
  id: string
  email: string
  displayName: string | null
  roles: string[]
}

export interface Session {
  accessToken: string
  refreshToken: string
  user: SessionUser
}

/** A unique email per call so tests never collide on OTP / rate-limit state. */
export function uniqueEmail(prefix = 'e2e'): string {
  const rand = Math.random().toString(36).slice(2, 8)
  return `${prefix}.${Date.now()}.${rand}@example.com`
}

/** Request an OTP and return the dev code from the response body. */
export async function requestOtp(request: APIRequestContext, email: string): Promise<string> {
  const res = await request.post(`${API_BASE_URL}/auth/otp/request`, { data: { email } })
  expect(res.ok(), `otp/request failed: ${res.status()} ${await res.text()}`).toBeTruthy()
  const body = await res.json()
  expect(
    body.otp,
    'No dev OTP in response — is APP_ENV local-like? (dev/local/test). Black-box OTP needs the dev code.',
  ).toBeTruthy()
  return String(body.otp)
}

/** Full programmatic login via the real OTP endpoints. */
export async function loginViaApi(request: APIRequestContext, email = uniqueEmail()): Promise<Session> {
  return await allure.step(`Войти через API по OTP (${email})`, async () => {
    const otp = await requestOtp(request, email)
    await attach('→ Запрос: POST /auth/otp/verify', { email, otp })
    await settle() // let the OTP write become visible before verifying
    const res = await request.post(`${API_BASE_URL}/auth/otp/verify`, { data: { email, otp } })
    expect(res.ok(), `otp/verify failed: ${res.status()} ${await res.text()}`).toBeTruthy()
    const session = (await res.json()) as Session
    await attach(`← Ответ: HTTP ${res.status()}`, session)
    await settle() // let the session/refresh rows settle before use
    return session
  })
}

/**
 * Inject a session into localStorage before any app code runs.
 *
 * The UI persists session atoms with Reatom's `withLocalStorage`, which stores a
 * RECORD ENVELOPE — `{ data, id, timestamp, to, version }` — not the raw value
 * (see @reatom/core reatomPersistWebStorage). Writing the raw value leaves the
 * atom null → AuthRouteGuard redirects to /login. So we mirror that envelope.
 */
export async function applySession(page: Page, session: Session): Promise<void> {
  await page.addInitScript((s) => {
    const rec = (data: unknown) =>
      JSON.stringify({
        data,
        id: 1,
        timestamp: Date.now(),
        to: Date.now() + 365 * 24 * 60 * 60 * 1000, // far-future expiry
        version: '1001', // @reatom/core persist VERSION
      })
    localStorage.setItem('session.accessToken', rec(s.accessToken))
    localStorage.setItem('session.refreshToken', rec(s.refreshToken))
    localStorage.setItem('session.user', rec(s.user))
  }, session)
}

/**
 * Intercept the OTP returned by the UI's own request (for tests that exercise
 * the on-screen login form rather than seeding the session). Resolves with the
 * 6-digit code from POST /auth/otp/request. Call BEFORE clicking "Send code".
 */
export async function interceptOtp(page: Page): Promise<string> {
  const res = await page.waitForResponse(
    (r) => r.url().includes('/auth/otp/request') && r.request().method() === 'POST',
    { timeout: 15_000 },
  )
  const body = await res.json()
  if (!body?.otp) {
    throw new Error('Intercepted otp/request had no dev OTP — backend is not local-like.')
  }
  return String(body.otp)
}

export interface SeedCell {
  id: string
  kind: 'code' | 'markdown'
  content: string
  updatedAt: number
}

function uuid(): string {
  // RFC4122-ish v4, good enough for test fixtures.
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (c) => {
    const r = (Math.random() * 16) | 0
    const v = c === 'x' ? r : (r & 0x3) | 0x8
    return v.toString(16)
  })
}

/** Create a notebook server-side via the API and return the response body. */
export async function seedNotebook(
  request: APIRequestContext,
  accessToken: string,
  opts: { title?: string; cells?: Array<{ kind: 'code' | 'markdown'; content: string }> } = {},
): Promise<{ id: string; title: string; cells: SeedCell[] }> {
  const now = Date.now()
  const cells: SeedCell[] = (opts.cells ?? []).map((c, i) => ({
    id: uuid(),
    kind: c.kind,
    content: c.content,
    updatedAt: now + i,
  }))
  return await allure.step(`Создать ноутбук через API: «${opts.title ?? 'Seeded notebook'}»`, async () => {
    const data = { id: uuid(), title: opts.title ?? 'Seeded notebook', formatVersion: 1, cells }
    await attach('→ Запрос: POST /notebooks', data)
    const res = await request.post(`${API_BASE_URL}/notebooks`, {
      headers: { Authorization: `Bearer ${accessToken}` },
      data,
    })
    expect(res.status(), `seedNotebook failed: ${res.status()} ${await res.text()}`).toBeLessThan(300)
    const body = (await res.json()) as { id: string; title: string; cells: SeedCell[] }
    await attach(`← Ответ: HTTP ${res.status()}`, body)
    await settle() // let the create become visible before the UI reads it
    return body
  })
}

/**
 * True if any of the user's notebooks (on the server) has a cell whose content
 * contains `needle`. Used to verify that a UI edit reached the backend via the
 * background autosync (#134) — i.e. it persists, not just lives in the editor.
 */
export async function serverHasCellContaining(
  request: APIRequestContext,
  accessToken: string,
  needle: string,
): Promise<boolean> {
  const headers = { Authorization: `Bearer ${accessToken}` }
  const list = await request.get(`${API_BASE_URL}/notebooks?limit=200`, { headers })
  if (!list.ok()) return false
  const items = (await list.json()).items as Array<{ id: string }>
  for (const item of items) {
    const res = await request.get(`${API_BASE_URL}/notebooks/${item.id}`, { headers })
    if (!res.ok()) continue
    const nb = (await res.json()) as { cells?: Array<{ content?: string }> }
    if (nb.cells?.some((c) => c.content?.includes(needle))) return true
  }
  return false
}

/**
 * Test fixtures:
 *  - `session`        — a real logged-in session (via API), unique per test.
 *  - `authedRequest`  — an APIRequestContext pre-authenticated with the session.
 *  - `authedPage`     — a Page that boots already signed in (session in storage).
 */
export const test = base.extend<{
  session: Session
  authedPage: Page
}>({
  session: async ({ request }, use) => {
    const session = await loginViaApi(request)
    await use(session)
  },
  authedPage: async ({ page, session }, use) => {
    await applySession(page, session)
    await use(page)
  },
})

export { expect }
