import { test, expect, seedNotebook } from '../fixtures/index'
import { SidebarPage } from '../pages/sidebar.page'

/**
 * AT-NB-04 (Regression) — delete a notebook from the sidebar row menu; it
 * disappears from the list. Only synced/backend notebooks expose Delete (the
 * floor "local" notebook does not — see AppSidebar #135), so we seed one via
 * the API first.
 * QA: TC-API-NB-*, TC-UI-NB-*, scenario E-06.
 */
test.describe('AT-NB-04 delete notebook @regression', () => {
  test('удаление ноутбука убирает его из сайдбара', async ({ authedPage, session, request }) => {
    const title = `ToDelete ${Date.now()}`
    const keeper = `Keeper ${Date.now()}`
    // Seed a SECOND notebook: the app forbids deleting the only notebook
    // (TARDIS-167 B-1), so with just one the row menu omits "Delete". See #183.
    await seedNotebook(request, session.accessToken, { title, cells: [{ kind: 'code', content: 'console.log(1)' }] })
    await seedNotebook(request, session.accessToken, { title: keeper })

    const sidebar = new SidebarPage(authedPage)
    await authedPage.goto('/')
    await expect(sidebar.rowByTitle(title)).toBeVisible({ timeout: 15_000 })

    await sidebar.delete(title)
    // Confirm dialog → confirm. The confirm action label is "Delete".
    await authedPage.getByRole('button', { name: /^Delete$/ }).last().click()

    await expect(sidebar.rowByTitle(title)).toHaveCount(0, { timeout: 15_000 })
  })
})
