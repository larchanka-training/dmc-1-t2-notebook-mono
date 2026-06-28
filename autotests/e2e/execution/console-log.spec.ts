import { test, expect, seedNotebook } from '../fixtures/index'
import { SidebarPage } from '../pages/sidebar.page'
import { NotebookPage } from '../pages/notebook.page'

/**
 * AT-EX-01 (Smoke) — run a code cell and see console.log output.
 * Execution is QuickJS/WASM in a Web Worker; output renders in
 * `data-output-segment` blocks under the cell.
 * QA: TC-UI-EXEC-01, scenario X-01.
 *
 * The code is SEEDED via the API (exact content) and the notebook is opened from
 * the sidebar, then run — the same proven pattern as multi-notebook-nav. This
 * avoids the boot demo notebook ("…full of features", ~9 cells) and the
 * CodeMirror-typing / insert-strip / create-navigation races that made the
 * type-it-in-the-UI variant flaky. See issue #183.
 */
test.describe('AT-EX-01 console.log output @smoke', () => {
  test('console.log появляется в выводе ячейки', async ({ authedPage, session, request }) => {
    const sidebar = new SidebarPage(authedPage)
    const notebook = new NotebookPage(authedPage)

    const nb = await seedNotebook(request, session.accessToken, {
      title: `AT-EX-01 ${Date.now()}`,
      cells: [{ kind: 'code', content: 'console.log("hello-e2e")' }],
    })
    await authedPage.goto('/')
    await notebook.waitForReady()
    await expect(sidebar.rowByTitle(nb.title)).toBeVisible({ timeout: 15_000 })
    await sidebar.openNotebook(nb.title)

    const cell = notebook.cellAt(0)
    await notebook.runCell(cell)
    await expect.poll(() => notebook.outputText(cell), { timeout: 20_000 }).toContain('hello-e2e')
  })
})
