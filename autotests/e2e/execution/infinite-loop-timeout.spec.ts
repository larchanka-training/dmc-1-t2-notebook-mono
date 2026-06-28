import { test, expect, seedNotebook } from '../fixtures/index'
import { SidebarPage } from '../pages/sidebar.page'
import { NotebookPage } from '../pages/notebook.page'

/**
 * AT-EX-03 (Regression) — an infinite loop is aborted by the runtime deadline
 * (DEFAULT_TIMEOUT_MS = 30s; a "timeout" status renders as data-state="halted").
 * The page stays responsive afterwards.
 * QA: TC-UI-EXEC-*, scenario X-02.
 *
 * The loop is SEEDED via the API (exact `while(true){}` — no CodeMirror typing
 * artifact that could turn it into terminating code) and opened from the sidebar,
 * then run. A second seeded cell gives the between-cells insert strip a stable
 * target for the responsiveness check. See issue #183.
 */
test.describe('AT-EX-03 infinite loop timeout @regression', () => {
  // 30s runtime deadline + UI/setup margin.
  test.setTimeout(90_000)

  test('while(true) прерывается по таймауту, страница работает', async ({ authedPage, session, request }) => {
    const sidebar = new SidebarPage(authedPage)
    const notebook = new NotebookPage(authedPage)

    const nb = await seedNotebook(request, session.accessToken, {
      title: `AT-EX-03 ${Date.now()}`,
      cells: [
        { kind: 'code', content: 'while(true){}' },
        { kind: 'code', content: 'const ok = 1' },
      ],
    })
    await authedPage.goto('/')
    await notebook.waitForReady()
    await expect(sidebar.rowByTitle(nb.title)).toBeVisible({ timeout: 15_000 })
    await sidebar.openNotebook(nb.title)

    const cell = notebook.cellAt(0)
    await notebook.runCell(cell)

    // Runtime deadline fires; the timeout status surfaces as data-state="halted".
    await expect(notebook.cellState(cell)).toHaveAttribute('data-state', 'halted', { timeout: 60_000 })

    // Page responsive: adding another cell still works (count grows).
    const before = await notebook.cells().count()
    await notebook.addCodeCell()
    await expect.poll(() => notebook.cells().count()).toBeGreaterThan(before)
  })
})
