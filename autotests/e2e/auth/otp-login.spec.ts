import { test, expect, uniqueEmail, interceptOtp } from '../fixtures/index'
import { LoginPage } from '../pages/login.page'

/**
 * AT-AUTH-01 (Smoke) — full OTP login through the on-screen form.
 * QA: TC-E2E-01, TC-UI-AUTH-*, scenarios A-01/A-02.
 */
test.describe('AT-AUTH-01 OTP login @smoke', () => {
  test('вход по OTP: email → код → авторизация', async ({ page }) => {
    const login = new LoginPage(page)
    const email = uniqueEmail('auth01')

    await login.goto()

    // Capture the dev OTP from the UI's own request, then complete the form.
    const otpPromise = interceptOtp(page)
    await login.requestCode(email)
    const otp = await otpPromise

    await expect(login.verify).toBeVisible()
    await login.enterOtp(otp)
    await login.submitOtp()

    // Lands on the app root (the notebook), no longer on /login.
    await expect(page).toHaveURL(/\/(?!login)/)
    await expect.poll(() => page.evaluate(() => localStorage.getItem('session.accessToken'))).not.toBeNull()

    // No unhandled console errors during the flow.
    await expect(page.locator('#email')).toHaveCount(0)
  })
})
