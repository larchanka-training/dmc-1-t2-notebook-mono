import { test, expect } from '../fixtures/index'
import { NotebookPage } from '../pages/notebook.page'

/**
 * AT-EX-02 (Regression) — a syntax error surfaces as an error in the cell
 * without crashing the app; the editor stays usable.
 * QA: TC-UI-EXEC-*, scenario X-04.
 */
test.describe('AT-EX-02 syntax error @regression', () => {
  test('синтаксическая ошибка показана, приложение отзывчиво', async ({ authedPage }) => {
    const notebook = new NotebookPage(authedPage)
    await authedPage.goto('/')

    const cell = await notebook.addCodeCell()
    await notebook.typeCode(cell, 'const x = {')
    await notebook.runCell(cell)

    // The cell reaches an error state and reports a SyntaxError.
    await expect(notebook.cellState(cell)).toHaveAttribute('data-state', 'error', { timeout: 15_000 })
    await expect.poll(() => notebook.outputText(cell)).toMatch(/SyntaxError/i)

    // App still responsive: another cell can still be added (count grows).
    const before = await notebook.cells().count()
    await notebook.addCodeCell()
    await expect.poll(() => notebook.cells().count()).toBeGreaterThan(before)
  })
})
