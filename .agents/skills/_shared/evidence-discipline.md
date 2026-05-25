# Evidence discipline

Shared reference. Loaded by `notebook-qa`,
`notebook-quality-analysis`, and `notebook-pr-review`. The same rules
apply to all three flows — test design, just-finished-work
verification, and PR review.

The verdict (or finding) is only useful when it's grounded in what
was actually observed. These rules apply to every claim in the
report or comment.

- **Don't rubber-stamp / Don't claim coverage you didn't observe.**
  A `pnpm test` run that ended with errors and was not re-run is
  not "tests pass". A scenario "tested via the autotest suite" is
  not covered unless that suite actually ran for this PR (note the
  `paths` filters — see `docs/github-actions-pr-checks.md`). State
  briefly what you checked: which sections, which CI logs, whether
  you ran tests locally, whether you opened the diff in the browser.

- **Don't invent commands you didn't run / Don't invent
  verification.** If you didn't run the tests, didn't open the
  staging deploy, didn't fetch the submodule pointer — say so.
  "Tests appear to pass" is not "tests pass". If you don't have a
  staging URL, you didn't smoke-test staging.

- **Distinguish evidence from inference.** "Verified locally:
  `pytest` green" vs. "Assumed safe: migration is idempotent". Both
  are useful; mixing them up is not. Same for review claims:
  "The `bump --dry-run` check is green on this PR" vs. "I assume
  the OpenAPI snapshot is fresh" — both fine; conflating them is
  not.

- **Concrete findings beat vague concerns.** "Possible N+1 in
  `notebooks_service.list:42`" beats "performance concerns".
  "Cross-feature import: `features/notebook/ui/X.tsx:42` imports
  from `@/features/auth/api` — see `fractal-frontend` §4" beats
  "feels like a boundary issue". If the concern is real, point at
  the line; if it's not, drop it.

- **Name what's good.** Silent approval / silent "Ready" is a
  weaker signal than explicit "well-tested" / "edge case handled
  cleanly" / "Section X is well-done".

- **State blockers clearly.** If `Not ready` / `Request changes`,
  name the blocker and what would unblock — don't dress it up as a
  "suggestion". Vague blocking language is a stall, not a verdict.

## Design-side specialisation

For `notebook-qa` (test design), the corresponding rule is:
**don't write tests that don't actually fail when the
implementation is broken**. Run the mental mutation test before
claiming a test "covers" a behaviour — if you swapped the
implementation for `return null`, would the test fail?

## Cross-link

- `.agents/skills/notebook-qa/SKILL.md` — design side
- `.agents/skills/notebook-quality-analysis/SKILL.md` — author-side
  verification before PR opens
- `.agents/skills/notebook-pr-review/SKILL.md` — reviewer side
