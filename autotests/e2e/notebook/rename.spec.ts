import { test, expect } from '../fixtures/index'
import { SidebarPage } from '../pages/sidebar.page'
import { NotebookPage } from '../pages/notebook.page'

/**
 * AT-NB-02 (Regression) — rename a notebook via the editable title; the new
 * name shows in the header and propagates to the sidebar row.
 * QA: TC-UI-NB-*, scenario E-05.
 *
 * Note: cross-reload persistence is intentionally NOT asserted here — a bare
 * reload of `/` returns to the local floor notebook (not this backend one), and
 * the sidebar exposes no stable per-notebook URL to reopen it. Server-side title
 * persistence is covered by the API suite (test_notebooks::test_patch_updates_title).
 */
test.describe('AT-NB-02 rename notebook @regression', () => {
  test('переименование обновляет заголовок и строку в сайдбаре', async ({ authedPage }) => {
    const sidebar = new SidebarPage(authedPage)
    const notebook = new NotebookPage(authedPage)
    const newName = `Renamed ${Date.now()}`

    await authedPage.goto('/')
    await notebook.waitForReady()
    await sidebar.createNotebook()
    await expect(notebook.title).toBeVisible()

    await notebook.setTitle(newName)
    await expect(notebook.title).toHaveText(newName)
    await expect(sidebar.rowByTitle(newName)).toBeVisible({ timeout: 15_000 })
  })
})
