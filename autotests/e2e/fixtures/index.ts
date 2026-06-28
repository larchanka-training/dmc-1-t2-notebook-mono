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
 * Provide `crypto.subtle.digest('SHA-1', …)` when the platform omits it.
 *
 * The E2E stack serves the UI over plain http://notebook.com — a NON-secure
 * context, so `window.crypto.subtle` is undefined (it is `[SecureContext]`-gated).
 * The app's boot derives the per-user demo-notebook id via `uuidV5` (SHA-1 over
 * `crypto.subtle`, ui/src/shared/lib/id.ts). Without it boot throws inside
 * `reconcileBootFromServer` BEFORE `loadNotebook`, so `notebookLoadedAtom` never
 * flips and the editor stays behind its loading skeleton — the failure behind the
 * 7 editor-dependent specs (title / cells / Code-Text strip never mount). Prod
 * runs over HTTPS (secure context) and uses the native implementation; this shim
 * installs only when native `subtle` is absent, so it never shadows real crypto.
 * SHA-1 is the ONLY digest the app uses (verified across the ui source); other
 * algorithms reject loudly so a new dependency can't pass silently. See issue #183.
 */
export async function installCryptoSubtleShim(page: Page): Promise<void> {
  await page.addInitScript(() => {
    const cryptoObj = globalThis.crypto as (Crypto & { subtle?: SubtleCrypto }) | undefined
    if (!cryptoObj || cryptoObj.subtle) return // native secure-context crypto — leave it

    // Spec-correct SHA-1 over a byte array → 20 bytes. Validated against Node's
    // crypto.createHash('sha1') (padding edges + fuzz) before landing.
    function sha1(bytes: Uint8Array): Uint8Array {
      const ml = bytes.length * 8
      const total = Math.ceil((bytes.length + 9) / 64) * 64
      const msg = new Uint8Array(total)
      msg.set(bytes)
      msg[bytes.length] = 0x80
      const dv = new DataView(msg.buffer)
      dv.setUint32(total - 8, Math.floor(ml / 0x100000000))
      dv.setUint32(total - 4, ml >>> 0)
      let h0 = 0x67452301, h1 = 0xefcdab89, h2 = 0x98badcfe, h3 = 0x10325476, h4 = 0xc3d2e1f0
      const w = new Int32Array(80)
      for (let i = 0; i < total; i += 64) {
        for (let j = 0; j < 16; j++) w[j] = dv.getInt32(i + j * 4)
        for (let j = 16; j < 80; j++) {
          const n = w[j - 3] ^ w[j - 8] ^ w[j - 14] ^ w[j - 16]
          w[j] = (n << 1) | (n >>> 31)
        }
        let a = h0, b = h1, c = h2, d = h3, e = h4
        for (let j = 0; j < 80; j++) {
          let f: number, k: number
          if (j < 20) { f = (b & c) | (~b & d); k = 0x5a827999 }
          else if (j < 40) { f = b ^ c ^ d; k = 0x6ed9eba1 }
          else if (j < 60) { f = (b & c) | (b & d) | (c & d); k = 0x8f1bbcdc }
          else { f = b ^ c ^ d; k = 0xca62c1d6 }
          const tmp = (((a << 5) | (a >>> 27)) + f + e + k + w[j]) | 0
          e = d; d = c; c = (b << 30) | (b >>> 2); b = a; a = tmp
        }
        h0 = (h0 + a) | 0; h1 = (h1 + b) | 0; h2 = (h2 + c) | 0; h3 = (h3 + d) | 0; h4 = (h4 + e) | 0
      }
      const out = new Uint8Array(20)
      const odv = new DataView(out.buffer)
      odv.setInt32(0, h0); odv.setInt32(4, h1); odv.setInt32(8, h2); odv.setInt32(12, h3); odv.setInt32(16, h4)
      return out
    }

    const subtle = {
      digest(algorithm: AlgorithmIdentifier, data: BufferSource): Promise<ArrayBuffer> {
        const name = typeof algorithm === 'string' ? algorithm : algorithm.name
        if (name !== 'SHA-1') {
          return Promise.reject(new Error(`e2e crypto.subtle shim: only SHA-1 implemented, got ${name}`))
        }
        const view =
          data instanceof ArrayBuffer
            ? new Uint8Array(data)
            : new Uint8Array(data.buffer, data.byteOffset, data.byteLength)
        return Promise.resolve(sha1(view).buffer)
      },
    }
    Object.defineProperty(cryptoObj, 'subtle', { value: subtle, configurable: true })
  })
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
    // The E2E origin (http://notebook.com) is not a secure context, so the app's
    // boot-time uuidV5 (crypto.subtle SHA-1) throws and the editor never mounts.
    // Supply the missing primitive before any app code runs. See issue #183.
    await installCryptoSubtleShim(page)
    await applySession(page, session)
    await use(page)
  },
})

export { expect }
