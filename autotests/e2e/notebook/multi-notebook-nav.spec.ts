import { test, expect, seedNotebook } from '../fixtures/index'
import { SidebarPage } from '../pages/sidebar.page'
import { NotebookPage } from '../pages/notebook.page'

/**
 * AT-NB-05 (Regression) — navigate between several notebooks; the editor shows
 * the selected notebook's content with no state bleed.
 * QA: TC-UI-NB-*, scenario E-07.
 */
test.describe('AT-NB-05 multi-notebook navigation @regression', () => {
  test('переключение ноутбуков меняет содержимое редактора', async ({ authedPage, session, request }) => {
    const alpha = `Alpha ${Date.now()}`
    const beta = `Beta ${Date.now()}`
    await seedNotebook(request, session.accessToken, { title: alpha, cells: [{ kind: 'code', content: 'const which = "ALPHA"' }] })
    await seedNotebook(request, session.accessToken, { title: beta, cells: [{ kind: 'code', content: 'const which = "BETA"' }] })

    const sidebar = new SidebarPage(authedPage)
    const notebook = new NotebookPage(authedPage)
    await authedPage.goto('/')

    await expect(sidebar.rowByTitle(alpha)).toBeVisible({ timeout: 15_000 })
    // Assertions are scoped to the code editor (.cm-content) so the sidebar row
    // titles ("Alpha …"/"Beta …") never satisfy a content check by accident.
    await sidebar.openNotebook(alpha)
    await expect(notebook.title).toHaveText(alpha)
    await expect(authedPage.locator('.cm-content').filter({ hasText: 'ALPHA' }).first()).toBeVisible()

    await sidebar.openNotebook(beta)
    await expect(notebook.title).toHaveText(beta)
    await expect(authedPage.locator('.cm-content').filter({ hasText: 'BETA' }).first()).toBeVisible()
    // No state bleed: the previous notebook's code is gone from the editor.
    await expect(authedPage.locator('.cm-content').filter({ hasText: 'ALPHA' })).toHaveCount(0)
  })
})
