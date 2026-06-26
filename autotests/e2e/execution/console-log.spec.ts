import { test, expect } from '../fixtures/index'
import { NotebookPage } from '../pages/notebook.page'

/**
 * AT-EX-01 (Smoke) — run a code cell and see console.log output.
 * Execution is QuickJS/WASM in a Web Worker; output renders in
 * `data-output-segment` blocks under the cell.
 * QA: TC-UI-EXEC-01, scenario X-01.
 */
test.describe('AT-EX-01 console.log output @smoke', () => {
  test('console.log появляется в выводе ячейки', async ({ authedPage }) => {
    const notebook = new NotebookPage(authedPage)
    await authedPage.goto('/')

    const cell = await notebook.addCodeCell()
    await notebook.typeCode(cell, 'console.log("hello-e2e")')
    await notebook.runCell(cell)

    await expect.poll(() => notebook.outputText(cell), { timeout: 20_000 }).toContain('hello-e2e')
  })
})
