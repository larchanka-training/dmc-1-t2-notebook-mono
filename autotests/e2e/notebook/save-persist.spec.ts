import { test, expect, serverHasCellContaining } from '../fixtures/index'
import { SidebarPage } from '../pages/sidebar.page'
import { NotebookPage } from '../pages/notebook.page'

/**
 * AT-NB-03 (Regression) — an edit made in the UI is durably persisted.
 * QA: TC-UI-NB-*, scenario E-04.
 *
 * Persistence is offline-first: cells autosave to IndexedDB as you type, and for
 * a signed-in user the edit also pushes to the server in the BACKGROUND (autosync
 * #134 — there is no manual "sync" button). We verify the meaningful contract —
 * the edit survives because it reached the backend — by polling the API until the
 * typed marker shows up server-side.
 *
 * Note: we create a fresh notebook first. The notebook opened at `/` is the LOCAL
 * floor/demo notebook, which is not pushed to the server; only created/owned
 * notebooks autosync (verified live: create → server count 0→1).
 */
test.describe('AT-NB-03 save & persist @regression', () => {
  test('правка в UI автоматически синхронизируется на сервер', async ({ authedPage, session, request }) => {
    const sidebar = new SidebarPage(authedPage)
    const notebook = new NotebookPage(authedPage)
    const marker = `persist_${Date.now()}`

    await authedPage.goto('/')
    await sidebar.createNotebook()
    // Wait for the new (empty) notebook editor to settle before adding a cell,
    // so the insert click doesn't race the create-navigation re-render.
    await expect(notebook.title).toBeVisible()
    const cell = await notebook.addCodeCell()
    await notebook.typeCode(cell, `const x = "${marker}"`)

    // Background autosync runs after the local autosave commits — poll the server
    // until the edit lands (nothing in the UI is clicked to trigger it).
    await expect
      .poll(() => serverHasCellContaining(request, session.accessToken, marker), {
        timeout: 40_000,
        intervals: [1000, 2000, 3000, 5000],
      })
      .toBe(true)
  })
})
