import { type Locator, type Page } from '@playwright/test'
import * as allure from 'allure-js-commons'

/**
 * SidebarPage (AT-INFRA-02) — the app sidebar.
 *
 * Real DOM (verified live): each notebook is a `<li>` row. The local notebook is
 * an `<a href="/">`; backend (synced) notebooks are a `<button>` whose text is
 * the title, with a sibling `<button aria-label="Notebook actions">` (… menu).
 * Rows are matched by their title TEXT, not by link role.
 */
export class SidebarPage {
  readonly page: Page
  readonly newNotebook: Locator

  constructor(page: Page) {
    this.page = page
    this.newNotebook = page.getByRole('button', { name: 'New notebook' })
  }

  async createNotebook(): Promise<void> {
    await allure.step('Создать новый ноутбук («New notebook»)', async () => {
      await this.newNotebook.click()
    })
  }

  /** Notebook rows = `<li>`s that carry a "Notebook actions" (…) button. */
  notebookRows(): Locator {
    return this.page.locator('li', { has: this.page.getByRole('button', { name: 'Notebook actions' }) })
  }

  /** The `<li>` row whose text is the given title. */
  rowByTitle(title: string): Locator {
    return this.page.locator('li').filter({ hasText: title }).first()
  }

  /** Open a notebook by clicking its row's primary control (button or link). */
  async openNotebook(title: string): Promise<void> {
    await allure.step(`Открыть ноутбук «${title}» из сайдбара`, async () => {
      await this.rowByTitle(title).getByRole('button').first().click()
    })
  }

  async openRowMenu(title: string): Promise<void> {
    await allure.step(`Открыть меню действий ноутбука «${title}»`, async () => {
      const row = this.rowByTitle(title)
      await row.hover()
      await row.getByRole('button', { name: 'Notebook actions' }).click()
    })
  }

  async rename(title: string): Promise<void> {
    await allure.step(`Выбрать «Rename» для «${title}»`, async () => {
      await this.openRowMenu(title)
      await this.page.getByRole('menuitem', { name: 'Rename' }).click()
    })
  }

  async delete(title: string): Promise<void> {
    await allure.step(`Выбрать «Delete» для «${title}»`, async () => {
      await this.openRowMenu(title)
      await this.page.getByRole('menuitem', { name: 'Delete' }).click()
    })
  }
}
