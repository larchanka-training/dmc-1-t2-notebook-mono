import { test, expect, uniqueEmail, interceptOtp } from '../fixtures/index'
import { LoginPage } from '../pages/login.page'

/**
 * AT-AUTH-02 (Regression) — invalid OTP is rejected and not "burned":
 * a subsequent attempt with the correct code still succeeds.
 * QA: TC-E2E-06, scenario A-03.
 */
test.describe('AT-AUTH-02 invalid OTP @regression', () => {
  test('неверный код — ошибка, верный код всё ещё работает', async ({ page }) => {
    const login = new LoginPage(page)
    const email = uniqueEmail('auth02')

    await login.goto()
    const otpPromise = interceptOtp(page)
    await login.requestCode(email)
    const realOtp = await otpPromise
    await expect(login.verify).toBeVisible()

    // Deliberately wrong code (kept distinct from the real one).
    const wrong = realOtp === '000000' ? '111111' : '000000'
    await login.enterOtp(wrong)
    await login.submitOtp()

    await expect(login.alert).toBeVisible()
    await expect(page).toHaveURL(/\/login/)

    // The real OTP was not consumed by the failed attempt.
    await login.enterOtp(realOtp)
    await login.submitOtp()
    await expect(page).toHaveURL(/\/(?!login)/)
  })
})
