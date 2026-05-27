---
name: notebook-pr-review
description: >
  PR review checklist for JS Notebook with all repo-specific rules
  baked in: submodule push order and pointer-bump discipline, auth.md
  synchronization across api/ and ui/, OpenAPI drift, no
  cross-feature imports in ui/, Reatom + clearStack/wrap rules, no
  amend/force-push on published commits, docs updated alongside code.
  Load this skill whenever reviewing a PR (manual review or after
  `/review`).
globs:
  - ".git/HEAD"
---

# notebook-pr-review

Review checklist consolidating every repo-specific rule that a
generic "looks good" pass would miss. Use it as a structured pass
over a PR — not as a script.

## Overview

This repo has three failure modes that a generic review will not
catch:

1. **Submodule drift** — pointer bumped to a commit that isn't pushed
   to the submodule's remote, or pushed in the wrong order.
2. **Contract drift** — `api/docs/openapi.json`, `api/docs/auth.md`,
   `ui/docs/auth.md` move independently of code or of each other.
3. **Architectural drift** — `useState`/`react-router`/cross-feature
   imports in `ui/`, Alembic-style ad-hoc migrations in `api/`, DDL in
   app startup, business logic in `shared/`.

This checklist is structured around those failure modes.

## Instruction priority

When this skill conflicts with `AGENTS.md`, the canonical docs under
`/docs`, or any submodule's own `AGENTS.md` / `docs/` — follow the
project-specific source. Severity labels and merge recommendations
below are formatting conventions, not overrides of project rules.
This skill is supplemental.

## When to use

Load this skill whenever reviewing a PR — manually, after a
`/review` agent pass, or before approving for merge. Pair with:

- `.agents/skills/merge-request-message/SKILL.md` if the PR
  description needs work
- `.agents/skills/notebook-qa/SKILL.md` if the QA evidence is thin
- `.agents/skills/notebook-ui/SKILL.md` / `notebook-api/SKILL.md`
  for the rules being enforced

## Process

**Read the tests first.** Tests show the author's intended behaviour
— what they think should be true after the change. Reviewing the
implementation without first knowing the intended behaviour usually
misses two findings: tests asserting the wrong thing, and
behaviour-changing PRs with no test at all. If there are no tests
where there should be, that is itself a review finding.

Then do a **high-level five-axis sweep** before walking the seven
project-specific sections. The sweep takes a minute and surfaces
big-shape problems that the rule-by-rule pass would only catch
incidentally.

### Five-axis sweep

| Axis | Quick check |
|---|---|
| **Correctness** | Does the code do what the PR claims? Edge cases handled? Partial updates safe? Date/time, pagination, filtering, sorting correct? |
| **Readability** | Names clear? Control flow obvious? Functions/components too large? Duplicated logic? Unnecessary cleverness? |
| **Architecture** | Follows existing patterns? Boundaries clean? Dependencies flow the right direction? Public contracts preserved? Unrelated concerns mixed? |
| **Security** | Input validated at the boundary? Authorization checked? Secrets protected? Queries parameterised? Untrusted data treated as untrusted (`AGENTS.md` §11)? |
| **Performance** | Queries bounded? Pagination on list endpoints? N+1? Expensive operations repeated? Async/sync boundaries respected? UI re-renders bounded? |

If any axis fires a major issue, surface it first — the seven
project-specific sections below assume the high-level shape is
sound.

### Seven project-specific sections

Pass through the seven sections below in order. The first three are
the ones most often missed.

### 1. Submodule discipline (`AGENTS.md` §2, §7)

When the PR touches `api/` or `ui/`:

- [ ] Submodule pointer bump is in **its own commit** in the monorepo
      (not mixed with monorepo file changes).
- [ ] The submodule commit referenced by the pointer is **already
      pushed** to the submodule's remote. Verify with:

```bash
git -C api log -1 $(git ls-tree HEAD api | awk '{print $3}')
# fails locally if you don't have the commit; in CI the
# `Checkout submodules` step will fail with 403 / "not found"
```

- [ ] The submodule's **own** PR (in `dmc-1-t2-notebook-api` /
      `dmc-1-t2-notebook-ui`) is **merged**, not just open. A bumped
      pointer to an open feature branch will become orphaned when
      that branch rebases.
- [ ] If both `api/` and `ui/` are touched and depend on each other
      (typical: API contract + ui consumer), both submodule PRs are
      merged before the monorepo PR can merge.

### 2. Documentation sync (`AGENTS.md` §9, §10)

The repo's rule is: **a change that affects logic described in a doc
is unfinished if the doc isn't updated in the same scope**.

- [ ] If `/docs/*.md` describes anything the PR changes — the doc is
      updated in the same PR. Common targets: `System_Architecture.md`,
      `execution-architecture.md`, `requirements.md`, `qa-plan.md`,
      `autotest-tasks.md`, `ci-cd.md`, `deploy.md`,
      `github-actions-pr-checks.md`, `github-repository-settings.md`,
      `Local-Proxy.md`.
- [ ] If `api/docs/auth.md` **or** `ui/docs/auth.md` is touched —
      **both** are updated in the same scope of work (`AGENTS.md` §10).
      The auth contract must not diverge between the two
      submodules. Editing one without the other counts as unfinished.
- [ ] If `AGENTS.md` itself describes anything that changes (purpose,
      structure, stack, run procedure, CI/CD, conventions) — it is
      updated in the same PR.

### 3. API contract & OpenAPI (`AGENTS.md` §7, notebook-api skill)

When the api side changes anything visible at the HTTP boundary:

- [ ] `api/docs/openapi.json` is regenerated via
      `python scripts/openapi.py dump` and committed.
- [ ] `openapi-version.yml` (`bump --dry-run`) is green on the PR.
      If it's red, the contributor missed the dump.
- [ ] If the change is visible to the ui — the **ui PR exists**, has
      run `pnpm api:generate`, and exposes the new endpoint through
      `@/shared/api/<domain>.ts` (no direct
      `@/shared/api/generated/**` imports in `features/`, `pages/`,
      `app/`).
- [ ] If a `required` field was added/removed or a path removed —
      `bump` will MAJOR-version. Confirm that the version jump is
      intentional and that the ui-side migration is staged.

### 4. UI-specific rules (`ui/AGENTS.md`, notebook-ui skill)

When the PR touches files under `ui/`:

- [ ] **No new `useState` / `useReducer` / `useEffect`-fetch / hand-
      rolled forms / `react-router` imports.** New code uses Reatom:
      `atom` / `computed` / `action`, `reatomRoute` / `urlAtom`,
      `reatomForm` / `reatomField`. Existing `useState` may persist
      during migrations but isn't added to new code.
- [ ] **Event handlers go through `wrap`.** Because `clearStack()`
      is enabled (`src/setup.ts`), `onClick={() => action()}` will
      throw `ReatomError: missing async stack` at click time. Look
      for raw arrow handlers in JSX.
- [ ] **HTTP only through `@/shared/api`** — no
      `@/shared/api/generated/**` imports from `features/`, `pages/`,
      or `app/`. ESLint should catch this but verify by eye.
- [ ] **No cross-feature imports.** `features/A` does not import
      from `features/B`. If it does — the boundary is wrong
      (`fractal-frontend` §4); ask the author to redraw, not work
      around.
- [ ] **Public API via `index.ts`** — imports from a module barrel,
      not internal paths. Exception: `shared/` has no barrel.
- [ ] **Domain-based file naming** — `model/user.ts`, not
      `model/types.ts`.
- [ ] **A feature folder isn't a single use-case.** `features/
      create-issue/` is wrong; that's a file inside an
      `issue-tracker` feature (`fractal-frontend` §3, §7-7).

### 5. API-specific rules (`api/README.md`, notebook-api skill)

When the PR touches files under `api/`:

- [ ] **DB schema changes ship as Liquibase changesets**
      (`liquibase/changelog/changes/`), included from
      `changelog-master.xml`, **append-only**. No raw SQL outside a
      changeset; no schema mutation from app startup.
- [ ] **Modular layout preserved**: each new module is
      `app/modules/<name>/{__init__.py, controllers/, services/, schemas/}`,
      router re-exported from `__init__.py`, included in `main.py`
      with `prefix=settings.api_prefix`. No dumping ground in `core/`.
- [ ] **`app.dependency_overrides` only in tests.** Production code
      shouldn't use it as a config switch.
- [ ] **No residue from the pre-OTP design.** `oauth_name_*`
      settings, password-based `/auth/login` (the stub flagged in
      `api/docs/auth.md` §1) — fine to keep during migration, but a
      PR adding **new** password-based code is a red flag.
- [ ] **`structlog`, not `print()`.** No bare `print` in app code.
- [ ] **Migrations / tests pair up.** A new module adds at least a
      basic `tests/test_<module>.py` using `dependency_overrides` for
      `get_db`.

### 6. Auth / security (`api/docs/auth.md`)

When auth or any secret-handling code changes:

- [ ] **OTP code is not returned in `prod` mode** (`auth.md` §6 —
      defence-in-depth). The handler must branch on `APP_ENV`. There
      should be a test locking this.
- [ ] **Refresh tokens are stored as hashes**, never plain
      (`auth.md` §3.2). Same for OTP codes (`auth.md` §4.2 —
      `code_hash`).
- [ ] **Refresh rotation has reuse-detection** (`auth.md` §2.2,
      §5.3). A new refresh endpoint without the reuse-detection
      branch is incomplete.
- [ ] **Rate limits are present** for `otp/request`, `otp/verify`,
      `refresh` (`auth.md` §11).
- [ ] **No secrets in responses, logs, or test fixtures.** JWT
      secret, refresh tokens, OTP codes (in prod), LLM API keys.
- [ ] **`auth.md` §10 biometrics** — placeholder only. A PR that
      starts implementing WebAuthn is out of scope and should be its
      own ticket.

### 7. History, CI, and PR text

- [ ] **No amend or force-push on published commits.** `AGENTS.md`
      §7 makes this explicit. Look at the PR commit list — if a
      commit hash is missing that was visible yesterday, that's a
      rewrite.
- [ ] **`main` is the only base.** Feature branches target `main`,
      not other feature branches (per `github-repository-settings.md`).
- [ ] **Commit messages follow a project pattern** documented in
      [`.agents/rules/commit-message-rule.md`](../../rules/commit-message-rule.md):
      `TARDIS-NN:`, Conventional Commits, or plain imperative — all
      accepted, no forced canon. Junk subjects ("fix", "wip") are
      not OK in a squash result.
- [ ] **Relevant CI checks are green.** Note the `paths` filters
      (`docs/github-actions-pr-checks.md`): a docs-only PR may show
      `API CI` / `UI CI` as **Skipped**, which is expected. A `Skipped`
      check on a PR that **did** touch `api/` or `ui/` is a red flag.
- [ ] **PR description matches the project template.** The
      `merge-request-message` skill produces a Problem / Solution /
      Verification / (Known issues / Screenshots / Notes) / Closes
      structure. A PR that's just "see commits" is too coarse —
      ask for at least 2–3 sentences in Problem and Solution.
- [ ] **`Closes #<NN>`** references a real GitHub issue (or
      `Refs TARDIS-NN` for tracker-only tickets without a GitHub
      issue).

## Format: severity, verdicts, output template

When **writing** the review (labels, verdicts, output shape), load
[`references/format.md`](./references/format.md). The labels in
short:

- **Critical** / **Important** block merge.
- **Suggestion** / **Nit** / **FYI** don't.
- Every review ends with exactly one verdict: **Approve** /
  **Approve with nits** / **Request changes** /
  **Needs clarification** / **Split recommended**.

Full severity table, examples, and the output template live in the
reference so the `SKILL.md` stays focused on the process.

## Evidence discipline

See [`_shared/evidence-discipline.md`](../_shared/evidence-discipline.md)
— the same rules apply across `notebook-qa`,
`notebook-quality-analysis`, and this skill. The verdict is only
useful when it's grounded in what was actually checked: don't
rubber-stamp, don't invent verification, distinguish evidence from
inference, concrete findings beat vague concerns, name what's
good, state blockers clearly.

## Review output template

When producing a structured review (e.g. in a comment, a
`gh pr review` body, or for the `/review` command), use this shape.
Omit any section that has nothing in it.

```markdown
# PR Review: <PR title or change name>

## Verdict
<Approve | Approve with nits | Request changes | Needs clarification | Split recommended>

## Summary
<1–3 sentences: what the PR does, overall assessment, the gating
finding if any.>

## What I checked
- <which Process sections were walked>
- <which CI logs were opened, which checks are green/skipped/red>
- <whether the diff was opened in a browser / whether the dev stack
  was run locally>

## Blocking findings (Critical / Important)

- **Critical/Important:** <Finding, with file:line if applicable>
  - Why it matters: <consequence — broken contract, security, lost
    data, AGENTS.md §X violation>
  - Suggested fix: <concrete action>

## Non-blocking comments (Suggestion / Nit / FYI)

- **Suggestion/Nit/FYI:** <Comment>

## Test review

**Good:**
- <covered behaviour, edge case caught, regression test added>

**Missing or weak:**
- <behaviour not covered, missing failure-path test, etc.>

## Risk areas

- <Risk and why it matters: e.g. "auth.md §5.3 reuse-detection has
  no integration test yet">

## Final notes

<Anything the author needs to know before the next revision —
follow-up tickets, deferred items, context they may lack.>
```

## Red flags

These are the patterns to call out by name in review comments:

- **Pointer bumped, submodule push missing** → "Push the submodule
  branch first, then bump the pointer (`AGENTS.md` §7)."
- **`auth.md` touched in one submodule only** → "The auth contract
  is documented in both `api/docs/auth.md` and `ui/docs/auth.md` —
  update both in the same scope (`AGENTS.md` §10)."
- **OpenAPI dry-run red** → "Run `python scripts/openapi.py dump`
  and commit `api/docs/openapi.json`."
- **`useState` / `react-router` in new ui code** → "Use Reatom
  primitives (`reatomRoute`, `atom`, `reatomForm`) — see
  `ui/.agents/skills/reatom/SKILL.md`."
- **Raw `onClick={() => action()}`** → "Wrap with `wrap()` —
  `clearStack()` is enabled and this will throw at click time
  (`ui/docs/architecture/reatom.md`)."
- **`@/shared/api/generated/**` import outside the facade** →
  "Route the call through `src/shared/api/<domain>.ts` and import
  from `@/shared/api`."
- **`features/A` imports from `features/B`** → "Cross-feature
  imports are forbidden — extract the shared concept to `entities/`
  or compose at a higher layer (`fractal-frontend` §4)."
- **DB schema change without a Liquibase changeset** → "Add a
  changeset under `liquibase/changelog/changes/` and include it from
  `changelog-master.xml`."
- **Manual edit to `api/docs/openapi.json`** → "This file is
  generated. Change the FastAPI route or Pydantic schema and re-run
  `dump`."
- **Bare `print()` in api code** → "Use `structlog`'s logger so
  output stays JSON-friendly."
- **Single use-case as a top-level feature folder
  (`features/create-issue/`)** → "Features are cohesive product
  blocks, not single user actions (`fractal-frontend` §3, §7-7) —
  fold into the parent feature."
- **PR description is `see commits`** → "Add at least 2–3 sentences
  in Problem and Solution — the `merge-request-message` skill has
  the template."

## Verification (the reviewer's own pre-approve checklist)

Before clicking Approve / Merge:

- [ ] All seven sections walked through; nothing flagged left
      unresolved.
- [ ] Relevant CI is green; `Skipped` checks are expected for this
      PR's paths.
- [ ] The reviewer (or the author) has manually exercised the
      change in the browser if it's user-visible (use
      `.agents/skills/notebook-qa/references/manual-test-checklist.md`).
- [ ] No unresolved conversation threads
      (`docs/github-repository-settings.md` "Require conversation
      resolution").
- [ ] If the PR updates submodule pointers — the submodule commits
      are reachable in their respective remotes.
- [ ] Tests were read before implementation; the review names what
      tests cover and what tests are missing.
- [ ] Five-axis sweep done before the seven project-specific
      sections.
- [ ] Every blocking comment is labeled `Critical` or `Important`.
- [ ] Review ends with exactly one merge verdict (Approve / Approve
      with nits / Request changes / Needs clarification / Split
      recommended).
- [ ] What was actually checked is stated (no "rubber-stamp" or
      invented verification — see Evidence discipline).

## Related

**Primary** (load alongside this skill):

- `AGENTS.md` §2 (submodules), §7 (branches/PR/OpenAPI), §9 (docs
  sync), §10 (`auth.md` sync), §11 (mandatory rules)
- [`references/format.md`](./references/format.md) — severity
  labels, verdicts, review output template
- [`_shared/evidence-discipline.md`](../_shared/evidence-discipline.md)
  — what counts as evidence in a review
- `docs/github-actions-pr-checks.md` — what CI checks mean,
  `paths`-filter behaviour
- `.agents/rules/commit-message-rule.md` — commit subject patterns
  (PR title becomes the squash subject on `main`)

**Secondary** (load only when the sub-topic of the PR demands it):

- `docs/github-repository-settings.md` — repo rules, PR template,
  merge strategy
- `.agents/skills/merge-request-message/SKILL.md` — PR text format
  (load when the PR description itself needs work)
- `.agents/skills/notebook-ui/SKILL.md` — ui rules being enforced
  (load for ui-touching PRs)
- `.agents/skills/notebook-api/SKILL.md` — api rules being enforced
  (load for api-touching PRs)
- `.agents/skills/notebook-llm/SKILL.md` — LLM-proxy rules (load
  when the PR touches `/llm/generate` or the WASM tier)
- `.agents/skills/notebook-api/references/openapi-sync.md` —
  contract workflow (load when openapi.json changed)
- `.agents/skills/notebook-api/references/liquibase-migrations.md`
  — DB change discipline (load when a changeset is in the diff)
- `.agents/skills/notebook-qa/SKILL.md` — test design (load when
  reviewing the PR's tests for design quality)
- `.agents/skills/notebook-quality-analysis/SKILL.md` — author-side
  verification before PR opens; review picks up where it left off
- `.agents/skills/notebook-qa/references/manual-test-checklist.md`
  — browser smoke (load for ui-touching or LLM PRs)
- `api/docs/auth.md` — auth contract used in §6 (load when auth
  files are in the diff)
