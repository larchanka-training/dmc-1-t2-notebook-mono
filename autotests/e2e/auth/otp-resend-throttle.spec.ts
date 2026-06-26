import { test, expect, uniqueEmail, interceptOtp } from '../fixtures/index'
import { LoginPage } from '../pages/login.page'

/**
 * AT-AUTH-04 (Regression) — after requesting a code, "Resend" is throttled with
 * a visible countdown (45s, see ui OtpInput/loginForm).
 * QA: TC-E2E-06, scenario A-05.
 */
test.describe('AT-AUTH-04 resend throttle @regression', () => {
  test('«Resend» заблокирован и показывает обратный отсчёт', async ({ page }) => {
    const login = new LoginPage(page)
    const email = uniqueEmail('auth04')

    await login.goto()
    const otpPromise = interceptOtp(page)
    await login.requestCode(email)
    await otpPromise
    await expect(login.verify).toBeVisible()

    // Immediately after sending, Resend is disabled and labelled "Resend in Ns".
    await expect(login.resend).toBeDisabled()
    await expect(login.resend).toHaveText(/Resend in \d+s/)
  })
})
