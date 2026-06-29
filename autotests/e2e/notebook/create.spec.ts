import { test, expect } from '../fixtures/index'
import { SidebarPage } from '../pages/sidebar.page'
import { NotebookPage } from '../pages/notebook.page'

/**
 * AT-NB-01 (Smoke) — create a new notebook from the sidebar.
 * QA: TC-UI-NB-01, scenario E-01.
 */
test.describe('AT-NB-01 create notebook @smoke', () => {
  test('«New notebook» открывает редактор', async ({ authedPage }) => {
    const sidebar = new SidebarPage(authedPage)
    const notebook = new NotebookPage(authedPage)

    await authedPage.goto('/')
    await notebook.waitForReady()
    await expect(sidebar.newNotebook).toBeVisible()

    const before = await sidebar.notebookRows().count()
    await sidebar.createNotebook()

    // The editor for the new notebook is shown (title is editable, present).
    await expect(notebook.title).toBeVisible()
    // The sidebar gained a notebook row.
    await expect.poll(() => sidebar.notebookRows().count()).toBeGreaterThan(before)
  })
})
