import { test, expect, seedNotebook } from '../fixtures/index'
import { SidebarPage } from '../pages/sidebar.page'
import { NotebookPage } from '../pages/notebook.page'

/**
 * AT-EX-02 (Regression) — a syntax error surfaces as an error in the cell
 * without crashing the app; the editor stays usable.
 * QA: TC-UI-EXEC-*, scenario X-04.
 *
 * The code is SEEDED via the API (exact content — no CodeMirror auto-close /
 * typing artifacts) and opened from the sidebar, then run. A second seeded cell
 * means the between-cells insert strip exists, so the "still responsive" check
 * (add a cell) has a stable target. See issue #183.
 */
test.describe('AT-EX-02 syntax error @regression', () => {
  test('синтаксическая ошибка показана, приложение отзывчиво', async ({ authedPage, session, request }) => {
    const sidebar = new SidebarPage(authedPage)
    const notebook = new NotebookPage(authedPage)

    const nb = await seedNotebook(request, session.accessToken, {
      title: `AT-EX-02 ${Date.now()}`,
      cells: [
        { kind: 'code', content: 'const x = {' },
        { kind: 'code', content: 'const ok = 1' },
      ],
    })
    await authedPage.goto('/')
    await notebook.waitForReady()
    await expect(sidebar.rowByTitle(nb.title)).toBeVisible({ timeout: 15_000 })
    await sidebar.openNotebook(nb.title)

    const cell = notebook.cellAt(0)
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
