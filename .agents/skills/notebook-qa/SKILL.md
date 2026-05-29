---
name: notebook-qa
description: >
  QA strategy and test design for JS Notebook — environment model,
  test pyramid, mapping changes to qa-plan.md §6 scenarios, picking
  the right test level, manual test checklist. Load when designing
  tests, writing autotests, planning what to cover, or filing a
  defect. For verifying that just-completed work is ready before
  PR review, use notebook-quality-analysis. For reviewing someone
  else's PR, use notebook-pr-review.
globs:
  - "api/tests/**"
  - "ui/**/*.test.ts"
  - "ui/**/*.test.tsx"
  - "ui/**/*.spec.ts"
  - "e2e/**"
  - "docs/qa-plan.md"
  - "docs/autotest-tasks.md"
---

# notebook-qa

Top-level orientation for QA strategy and test design on JS
Notebook. Routes the task to the right doc, the right tool, and the
right scenario list.

> This skill is the **design / strategy** side of QA — picking
> levels, mapping to scenarios, planning what to cover. For
> verifying that a *just-completed* implementation is actually
> ready, load
> [`notebook-quality-analysis`](../notebook-quality-analysis/SKILL.md)
> instead.

## Overview

The authoritative documents are:

- `docs/qa-plan.md` — strategy: goals, scope, environments, metrics,
  numbered scenarios (A-NN, E-NN, X-NN, S-NN, R-NN, L-NN), defect SLA,
  CI/CD quality gates
- `docs/autotest-tasks.md` — Playwright E2E roadmap: 29 tasks, smoke
  subset, file layout (`e2e/<feature>/<spec>.spec.ts`)

This skill is the entry point that **routes** to those docs and
records what is runnable **today** vs. **planned**.

## Instruction priority

When this skill conflicts with `AGENTS.md`, `docs/qa-plan.md`,
`docs/autotest-tasks.md`, or any submodule's own testing
documentation — follow the project-specific source. This skill is
supplemental.

## Environments

Per `docs/qa-plan.md` §5. All on AWS, staging mirrors production
(same instance types, S3 buckets with separate namespaces, email
provider in sandbox mode):

| Env | Purpose | Where it runs |
|---|---|---|
| Local | Developer self-check | Developer machine via `./start-services.sh` |
| CI | Per-PR automated checks | GitHub Actions |
| Staging | Pre-release E2E + manual exploration | AWS (planned; deploy currently dry-run, see `docs/deploy.md`) |
| Production | Live users | AWS, manual promotion from staging |

> Staging is the **target** state. Today the `Manual Deploy` workflow
> is a dry-run (`docs/deploy.md`) — real AWS hosts are upcoming. QA
> activities that depend on staging (E2E, manual exploration) need
> the local stack until then.

## Test pyramid — runnable today

```
                     ┌─ Manual exploration ─┐
                     │  in browser, by hand │
                     │  (use references/    │
                     │   manual-test-       │
                     │   checklist.md)      │
                     └──────────────────────┘
                  ┌─ docker-compose smoke ──┐
                  │  full stack boots,      │
                  │  proxy + api + ui +     │
                  │  postgres up            │
                  └─────────────────────────┘
              ┌─ Integration (api side) ────┐
              │  pytest + TestClient,       │
              │  dependency_overrides for   │
              │  get_db; no real Postgres   │
              └─────────────────────────────┘
       ┌─ Unit (ui side) ───────────────────┐
       │  Vitest + Testing Library          │
       └────────────────────────────────────┘
┌─ Static ──────────────────────────────────┐
│  ESLint (ui), Ruff (api), tsc typecheck   │
└───────────────────────────────────────────┘
```

## Planned but not wired yet

- **Playwright E2E** — `docs/autotest-tasks.md` defines the 29 tasks
  and `e2e/` layout. No specs exist in the repo yet. Smoke subset
  (`AT-AUTH-01`, `AT-NB-01`, `AT-EX-01`, `AT-SH-01`, `AT-LLM-01`)
  blocks PRs **once implemented**.
- **SonarQube Quality Gate** — strategy in `docs/qa-plan.md` §5.1
  (coverage ≥ 70%, 0 critical/blocker, duplication < 3%). Not enabled
  in CI yet.
- **API tests (pytest + httpx)** outside the existing module suite —
  the contract tests (R-01..R-14 in qa-plan) are not yet implemented.
- **Coverage reporting** — target ≥ 70% per qa-plan §5.2; not enforced
  in CI yet.

When extending QA — pick from this list before inventing new
mechanisms. Each item has a documented shape; don't reinvent.

## When to use

Load this skill when:

- Designing tests for a new feature (which level? which scenarios?)
- Writing or reviewing autotests in `api/tests/` or `ui/src/**/*.test.ts*`
- Adding Playwright E2E specs (follow `docs/autotest-tasks.md`)
- Planning a manual browser walk for a feature in flight — pick
  sections from
  [`references/manual-test-checklist.md`](./references/manual-test-checklist.md)
- Filing a defect — use the bug template in `qa-plan.md` §8

Load a **different** skill when:

- Verifying that a *just-finished* implementation is ready before
  opening / merging a PR →
  [`notebook-quality-analysis`](../notebook-quality-analysis/SKILL.md)
- Reviewing someone else's PR →
  [`notebook-pr-review`](../notebook-pr-review/SKILL.md)

## Process

### 1. Pick the right level for a new test

| Concern | Level | Tool | Where |
|---|---|---|---|
| Pure function, isolated logic | Unit | Vitest (ui) / pytest (api) | next to the source |
| Component rendering, props, events | Unit | Vitest + Testing Library | next to the component |
| API contract (status, schema, headers) | Integration | pytest + `TestClient` | `api/tests/` |
| Full user flow across api + ui | E2E | Playwright (when wired) | `e2e/<feature>/<spec>.spec.ts` |
| Full stack boots, services talk | Smoke | docker-compose | `.github/workflows/docker-compose-ci.yml` (already in CI) |

Rule: **mock at the layer you're testing, not below**. ui unit tests
should not call the real `api/`; api integration tests should not
use a real Postgres (override `get_db`).

### 2. Map the change to a qa-plan scenario

Before writing the test, find the matching scenario in `docs/qa-plan.md`
§6 (A-NN / E-NN / X-NN / S-NN / R-NN / L-NN). If a matching scenario
doesn't exist:

1. Add the scenario to `qa-plan.md` §6 in the same PR
2. If it's a smoke-worthy scenario, also queue it as an `AT-*` task in
   `docs/autotest-tasks.md` (or update the existing one if it's a
   refinement)

This keeps the strategy doc and the test code in sync. See
`AGENTS.md` §9 on docs sync.

### 3. Run the checks locally

```bash
# ui
cd ui
pnpm lint
pnpm typecheck
pnpm test

# api
cd api
ruff check .
pytest

# full stack smoke (matches CI)
./start-services.sh   # then exercise the flow manually
```

Failing locally just delays the loop.

### 4. Manual verification in the browser

For any user-visible change, run the dev stack and exercise the
feature by hand. Use
[`references/manual-test-checklist.md`](./references/manual-test-checklist.md)
to make sure you didn't miss a related flow.

Type checking and unit tests verify code correctness, not feature
correctness. If you can't test the UI manually, say so in the PR
description rather than claiming success.

### 5. Filing a defect

Use the bug template from `qa-plan.md` §8:

- Severity: Blocker / Critical / Major / Minor
- Repro steps + Expected vs. Actual
- Environment + browser + commit
- Console log + network HAR + backend log if relevant
- Link to the related scenario (A-04, X-02, …) if applicable

## Evidence discipline

See [`_shared/evidence-discipline.md`](../_shared/evidence-discipline.md)
— shared across `notebook-qa`, `notebook-quality-analysis`, and
`notebook-pr-review`. Don't claim coverage you didn't observe,
don't invent commands, distinguish evidence from assumption,
concrete findings over vague concerns, name what's good, state
blockers clearly.

The design-side specialisation: **don't write tests that don't
actually fail when the implementation is broken**. Run the mental
mutation test before claiming a test "covers" a behaviour — if you
swapped the implementation for `return null`, would the test fail?

## Red flags

- **A new feature without a matching scenario in `qa-plan.md` §6** —
  either the doc is stale or the scope is fuzzy. Add the scenario in
  the same PR; otherwise the test surface drifts from the strategy.
- **A unit test that needs the real api running** — the boundary is
  wrong. Move it to integration (api side) or mock the HTTP layer
  (ui side via MSW or test wrappers).
- **A pytest that talks to a real Postgres** — use
  `app.dependency_overrides` for `get_db`. Integration tests that
  genuinely require a DB should be marked and not run by default.
- **A Playwright spec that depends on real email delivery** — use the
  `interceptOtp(page)` helper from `e2e/fixtures/index.ts` (sandbox
  mode), per `AT-INFRA-01`. Never make a real inbox a CI dependency.
- **A test asserting on UI text in production language only** —
  internationalisation is light in this repo, but the assertion should
  match the locale that the test sets, not the developer's machine.
- **A regression that escapes to staging because nothing exercises
  it locally** — likely a missing smoke scenario. Add to
  `autotest-tasks.md`.
- **"Tests pass, ship it" without manual browser check on a UI PR** —
  see `ui/AGENTS.md` and `notebook-ui` skill. Tests prove code; the
  human proves the feature.

## Lifecycle handoff

This skill is the **design** side of QA. Once tests are written and
the implementation claims to be ready, the next step is **not** to
re-run this skill — it's to switch to
[`notebook-quality-analysis`](../notebook-quality-analysis/SKILL.md),
which produces a `Ready` / `Ready with caveats` / `Not ready`
verdict against the implementation. Then `notebook-pr-review` when
opening / reviewing the PR.

`notebook-qa` → `notebook-quality-analysis` → `notebook-pr-review`
is the canonical flow. Loading only this skill at the end of
implementation means skipping the verification verdict — that is
the most common miss in this lifecycle.

## Verification

Before claiming QA work done:

- [ ] Static: `pnpm lint`, `pnpm typecheck`, `ruff check .` clean
- [ ] Unit/integration: `pnpm test`, `pytest` green
- [ ] If the change is user-visible — the relevant section of
      [`references/manual-test-checklist.md`](./references/manual-test-checklist.md)
      walked through in the browser
- [ ] Affected qa-plan scenarios (A-NN / E-NN / …) covered, or new
      scenarios added to `docs/qa-plan.md` §6 in the same PR
- [ ] If the test belongs to the Playwright roadmap — the matching
      `AT-*` task in `docs/autotest-tasks.md` updated (status, scope,
      file path) in the same PR
- [ ] No real-Postgres, real-email, or real-LLM dependency added to
      CI
- [ ] If `docs/qa-plan.md` or `docs/autotest-tasks.md` describe
      anything this change affects — both updated in the same PR
      (`AGENTS.md` §9)

## Related

**Primary** (load alongside this skill):

- `docs/qa-plan.md` — QA strategy, scenarios, gates, defect SLA
- `docs/autotest-tasks.md` — Playwright E2E roadmap (29 tasks +
  smoke subset)
- [`references/manual-test-checklist.md`](./references/manual-test-checklist.md)
  — shared resource (also used by `notebook-quality-analysis` and
  `notebook-pr-review`)
- [`_shared/evidence-discipline.md`](../_shared/evidence-discipline.md)
  — what counts as evidence in QA work
- `AGENTS.md` §5 (tests and checks), §9 (docs sync)

**Secondary** (load only when the sub-topic comes up):

- [`notebook-quality-analysis`](../notebook-quality-analysis/SKILL.md)
  — load **after** implementation, to verify it's ready (the
  lifecycle successor of this skill)
- `docs/execution-architecture.md` — the code execution model
  scenarios X-NN should match (QuickJS WASM Web Worker)
- `.agents/skills/notebook-ui/SKILL.md` — ui-side checks
- `.agents/skills/notebook-api/SKILL.md` — api-side checks (pytest,
  `dependency_overrides`)
- `.agents/skills/notebook-llm/SKILL.md` — LLM-specific scenarios
  (L-NN), mocking the provider chain
- `.agents/skills/notebook-pr-review/SKILL.md` — review checklist
  that incorporates QA verification
