import { type Locator, type Page, expect } from '@playwright/test'
import * as allure from 'allure-js-commons'

/**
 * LoginPage (AT-INFRA-02) — passwordless OTP login at `/login`.
 * Selectors verified against ui/src/features/auth/ui/LoginForm.tsx + OtpInput.tsx.
 * Public methods are wrapped in Allure steps (Russian) for a readable report.
 */
export class LoginPage {
  readonly page: Page
  readonly email: Locator
  readonly sendCode: Locator
  readonly verify: Locator
  readonly resend: Locator
  readonly backToEmail: Locator
  readonly alert: Locator

  constructor(page: Page) {
    this.page = page
    this.email = page.locator('#email')
    this.sendCode = page.getByRole('button', { name: /Send code|Sending/ })
    this.verify = page.getByRole('button', { name: /^(Verify|Verifying)/ })
    this.resend = page.getByRole('button', { name: /Resend/ })
    this.backToEmail = page.getByRole('button', { name: /Use a different email/ })
    this.alert = page.getByRole('alert')
  }

  async goto(): Promise<void> {
    await allure.step('Открыть страницу входа /login', async () => {
      await this.page.goto('/login')
      await expect(this.email).toBeVisible()
    })
  }

  async requestCode(email: string): Promise<void> {
    await allure.step(`Ввести email (${email}) и запросить код`, async () => {
      await this.email.fill(email)
      await this.sendCode.click()
    })
  }

  /** Type the 6-digit code into the per-digit inputs (aria-label "Digit N"). */
  async enterOtp(code: string): Promise<void> {
    await allure.step(`Ввести 6-значный код: ${code}`, async () => {
      const digits = code.padStart(6, '0').slice(0, 6).split('')
      for (let i = 0; i < 6; i++) {
        await this.page.getByLabel(`Digit ${i + 1}`).fill(digits[i])
      }
    })
  }

  async submitOtp(): Promise<void> {
    await allure.step('Подтвердить код', async () => {
      await this.verify.click()
    })
  }
}
