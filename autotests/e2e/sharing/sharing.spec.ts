import { test } from '../fixtures/index'

/**
 * AT-SH-01..04 (Sharing) — NOT AUTOMATABLE in this build.
 *
 * KNOWN LIMITATION (release-report §Known limitations): the sharing feature is
 * not implemented. There is no generate-link / revoke UI (the AppSidebar row
 * menu's "Duplicate" is disabled and there is no share entry), and the backend
 * exposes no share endpoints (notebooks are strictly owner-scoped). The roadmap
 * specs AT-SH-01 (smoke), AT-SH-02/03 (regression), AT-SH-04 (edge) and the
 * qa/ui/sharing.md / qa/e2e sharing cases therefore cannot run.
 *
 * Verified against ui@0082a09 (AppSidebar.tsx) and api@8439b84 (no share routes).
 * These are kept as skipped placeholders so the traceability matrix stays
 * complete; convert to real tests when sharing ships.
 */
test.describe('Sharing @blocked', () => {
  test.skip('AT-SH-01 generate & open share link — sharing not implemented', () => {})
  test.skip('AT-SH-02 guest executes shared notebook — sharing not implemented', () => {})
  test.skip('AT-SH-03 revoke share link — sharing not implemented', () => {})
  test.skip('AT-SH-04 share link of deleted notebook — sharing not implemented', () => {})
})
