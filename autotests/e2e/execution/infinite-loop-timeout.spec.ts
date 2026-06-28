import { test, expect } from '../fixtures/index'
import { NotebookPage } from '../pages/notebook.page'

/**
 * AT-EX-03 (Regression) — an infinite loop is aborted by the runtime deadline
 * (DEFAULT_TIMEOUT_MS = 30s; a "timeout" status renders as data-state="halted").
 * The page stays responsive afterwards.
 * QA: TC-UI-EXEC-*, scenario X-02.
 */
test.describe('AT-EX-03 infinite loop timeout @regression', () => {
  // 30s runtime deadline + UI/setup margin.
  test.setTimeout(90_000)

  test('while(true) прерывается по таймауту, страница работает', async ({ authedPage }) => {
    const notebook = new NotebookPage(authedPage)
    await authedPage.goto('/')
    await notebook.waitForReady()

    const cell = await notebook.addCodeCell()
    await notebook.typeCode(cell, 'while(true){}')
    await notebook.runCell(cell)

    // Runtime deadline fires; the timeout status surfaces as data-state="halted".
    await expect(notebook.cellState(cell)).toHaveAttribute('data-state', 'halted', { timeout: 60_000 })

    // Page responsive: adding another cell still works (count grows).
    const before = await notebook.cells().count()
    await notebook.addCodeCell()
    await expect.poll(() => notebook.cells().count()).toBeGreaterThan(before)
  })
})
