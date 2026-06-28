import { type Locator, type Page, expect } from '@playwright/test'
import * as allure from 'allure-js-commons'

/**
 * NotebookPage (AT-INFRA-02) — the editor: title, cells, run controls, output.
 * Verified against ui/src/features/notebook/ui/{NotebookView,NotebookCell,
 * NotebookHeader,NotebookToolbar,OutputView,CodeEditor}.tsx.
 *
 * Note: cells use CodeMirror 6 (`.cm-host` → `.cm-content` contenteditable);
 * output segments carry `data-output-segment="true"`.
 */
export class NotebookPage {
  readonly page: Page
  readonly title: Locator
  readonly runAll: Locator

  constructor(page: Page) {
    this.page = page
    this.title = page.getByLabel('Notebook title')
    this.runAll = page.getByRole('button', { name: /Run All|^Stop$/ })
  }

  /**
   * Wait for the boot-time gate to clear and the editor body to mount.
   *
   * For a signed-in user NotebookPage renders an `aria-busy` skeleton until boot
   * un-gates `notebookLoadedAtom`, and that happens only AFTER a network reconcile
   * (ui: setup.ts → reconcileBootFromServer → loadNotebook). Under CI load that
   * round-trip can exceed the default 10s expect timeout, so the title / cells /
   * insert-strip mount late and a bare interaction races the skeleton (the title
   * and the "Code" pill simply aren't there yet). Gate editor work on this
   * readiness wait — once the title is visible the body is mounted — instead of
   * racing the boot. Generous cap so a slow boot waits; a genuinely broken editor
   * still fails (once) within it.
   *
   * See https://github.com/larchanka-training/dmc-1-t2-notebook-mono/issues/183
   */
  async waitForReady(): Promise<void> {
    await allure.step('Дождаться готовности редактора (boot)', async () => {
      await expect(this.title).toBeVisible({ timeout: 30_000 })
    })
  }

  cells(): Locator {
    return this.page.locator('[data-cell-id]')
  }

  cellAt(index: number): Locator {
    return this.cells().nth(index)
  }

  /** All code editors (CodeMirror `.cm-content`) currently mounted. */
  codeEditors(): Locator {
    return this.page.locator('.cm-content')
  }

  /**
   * Add a new code cell via the insert-strip "Code" pill and return the cell
   * wrapper that holds the newly-mounted editor. Targeting by `.cm-content`
   * (not by index) skips any markdown cell sitting at index 0.
   */
  async addCodeCell(): Promise<Locator> {
    return await allure.step('Добавить ячейку кода', async () => {
      const before = await this.codeEditors().count()
      await this.page.getByRole('button', { name: 'Code', exact: true }).first().click()
      await expect.poll(() => this.codeEditors().count(), { timeout: 15_000 }).toBeGreaterThan(before)
      return this.page.locator('[data-cell-id]', { has: this.page.locator('.cm-content') }).last()
    })
  }

  /** Add a new text (markdown) cell via the "Text" pill. */
  async addTextCell(): Promise<void> {
    await allure.step('Добавить текстовую (markdown) ячейку', async () => {
      await this.page.getByRole('button', { name: 'Text', exact: true }).first().click()
    })
  }

  /** Type code into a cell's CodeMirror editor (replaces existing content). */
  async typeCode(cell: Locator, code: string): Promise<void> {
    await allure.step(`Ввести код в ячейку: ${code}`, async () => {
      const editor = cell.locator('.cm-content')
      await editor.click()
      await this.page.keyboard.press('ControlOrMeta+a')
      await this.page.keyboard.press('Delete')
      await editor.pressSequentially(code)
    })
  }

  async runCell(cell: Locator): Promise<void> {
    await allure.step('Запустить ячейку («Run cell»)', async () => {
      await cell.getByRole('button', { name: 'Run cell' }).click()
    })
  }

  /** Combined output text of a cell (all `data-output-segment` blocks). */
  async outputText(cell: Locator): Promise<string> {
    const segments = cell.locator('[data-output-segment="true"]')
    await expect(segments.first()).toBeVisible({ timeout: 15_000 })
    return (await segments.allInnerTexts()).join('\n')
  }

  /** The cell's lifecycle state, from the `data-state` attribute on <article>. */
  cellState(cell: Locator): Locator {
    return cell.locator('article[data-state]')
  }

  async setTitle(value: string): Promise<void> {
    await allure.step(`Переименовать ноутбук в «${value}»`, async () => {
      await this.title.click()
      await this.page.keyboard.press('ControlOrMeta+a')
      await this.page.keyboard.press('Delete')
      await this.page.keyboard.type(value)
      await this.title.blur()
    })
  }
}
