import { test, expect } from '../fixtures/index'

/**
 * AT-AUTH-05 (Regression) — protected routes redirect unauthenticated users to
 * /login?from=<path>. The protected route is the notebook at `/` (guarded by
 * AuthRouteGuard); there is no separate `/dashboard` in this build.
 * QA: TC-E2E-07, scenario A-06.
 */
test.describe('AT-AUTH-05 unauthenticated redirect @regression', () => {
  test('вход на ноутбук без сессии редиректит на /login', async ({ page }) => {
    // Start clean: no tokens in storage.
    await page.addInitScript(() => localStorage.clear())
    await page.goto('/')
    await expect(page).toHaveURL(/\/login(\?from=)?/)
    await expect(page.locator('#email')).toBeVisible()
  })
})
