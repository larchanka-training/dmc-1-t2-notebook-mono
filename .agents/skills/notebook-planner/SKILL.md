---
name: notebook-planner
description: >
  Task decomposition skill for JS Notebook monorepo. Load this skill
  before starting any non-trivial task — it routes the work across
  the two submodules (`api/`, `ui/`), the monorepo, and `/docs`, and
  enforces the submodule push order, doc sync rules (`auth.md`,
  OpenAPI), and branch/PR discipline (`main` is protected, no direct
  pushes, no amend on published commits).
globs:
  - "AGENTS.md"
  - ".agents/**"
  - "docs/**"
---

# notebook-planner

The first skill to load for any non-trivial task. Decomposes the
work into submodule-aware steps with the right ordering, and tells
you which other skill to load for each step.

## Overview

JS Notebook is a monorepo with two git submodules (`api/`, `ui/`).
Most real tasks touch more than one place. Decomposing them
sequentially — and in the right submodule order — is the difference
between a clean merge and an orphaned pointer.

Three things this skill optimises for:

1. **Which submodules will be touched** — `api/`, `ui/`, monorepo
   root, `/docs`, `proxy/`, or `.github/workflows/`.
2. **Cross-submodule contracts** — OpenAPI snapshot, `auth.md` pair.
3. **Push and PR order** — submodule first, then monorepo pointer;
   contract-side first, consumer-side second.

## Instruction priority

When this skill conflicts with `AGENTS.md`, the canonical docs under
`/docs`, or any submodule's own `AGENTS.md` / `docs/` — follow the
project-specific source. The plan this skill produces is constrained
by those documents, not the other way around. This skill is
supplemental.

## When to use

Load this skill at the start of any task that is not a one-file
fix. Specifically:

- A new feature spanning api + ui
- A schema, API, or auth change (touches `auth.md` and/or OpenAPI)
- Anything that updates a `/docs/*.md` whose logic is described in
  code
- Any work that crosses submodule boundaries

## When NOT to load this skill

Skip the planner — go straight to the specialist skill — when
**all** of these hold:

- The change is < 30 lines of non-mechanical diff.
- It touches **one** submodule (or only `/docs` cosmetics).
- There is **no** contract change (no OpenAPI shape, no `auth.md`,
  no DB schema, no new env var).
- There is **no** cross-doc impact (no `/docs/*.md` whose logic the
  change describes).

In that case load `notebook-ui` **or** `notebook-api` directly. The
planner is overhead for one-file fixes; loading it on every task
trains the agent (and reviewer) to skim it. Save it for changes
where the sequencing matters.

If any of the four conditions fail, load the planner.

## Skills are heuristics, not proofs

A clean plan and a green Verification checklist are *necessary*,
not *sufficient*. Skills cover the failure modes the team has
observed before — they do not predict the failure modes specific
to this change. After the structured plan, spend a minute on:

- **What is novel about this task** that no skill anticipates?
- **What could break that the Verification section doesn't catch?**

Surface those in the **Risks** section of the plan, not as a
footnote. "I followed the skill" is not the same as "the change is
safe". Same rule applies in `notebook-quality-analysis` and
`notebook-pr-review`.

## Load budget — which skills to actually keep open

Loading every cross-linked skill is the default failure mode. Use
this table — pick the row that matches the task size (from the
sizing rubric below) and load only what the row prescribes.

| Task size | Load alongside planner | Add on demand |
|---|---|---|
| **XS / S** | One specialist (`notebook-ui` **or** `notebook-api`, **or** `notebook-llm` if LLM-touching) | none — skip planner per "When NOT to load" above and load only the specialist |
| **M** | Planner + one specialist + `notebook-qa` (test design) | `notebook-llm` if LLM-touching; `notebook-api/references/openapi-sync.md` if contract changes |
| **L** | Planner + both specialists (`ui` + `api`) + `notebook-qa` + `notebook-quality-analysis` | `notebook-llm` if LLM-touching; relevant references (`openapi-sync.md`, `liquibase-migrations.md`, `manual-test-checklist.md`) |
| **XL** | Stop and split before loading anything (`Split triggers` below) | n/a |

PR-time skills (`notebook-pr-review`, `merge-request-message`) are
**not** part of the implementation load budget — load them at PR
authoring / review time, not during implementation.

The `Related` section of every skill marks **primary** vs.
**secondary** links. Primary = load at the same time. Secondary =
load only when the sub-topic comes up. Following every link by
default puts you over budget within two hops.

## Process

### 1. Read the task

Read the issue or the ask. Pull the ticket if there is one:

```bash
# branch like feature/TARDIS-15-bump-submodules
git branch --show-current
# pull GitHub issue if a #NN is referenced
gh issue view <NN>
```

Capture: what the user observes today vs. what they should observe
after. The "what" — not the "how".

### 2. Identify the surface (which places change)

Walk through the table below and check each row. Multiple rows can
match.

| Touched | Signal |
|---|---|
| `api/` | New endpoint, schema, DB column, migration, auth flow |
| `ui/` | New page/route, component, form, state, HTTP consumer |
| `api/docs/openapi.json` | API contract changed at all (path, schema, field, response code, required flag) |
| `api/docs/auth.md` **and** `ui/docs/auth.md` | Anything about OTP / JWT / refresh / sessions / notebook persistence / conflict resolution |
| `/docs/*.md` | Architecture, execution model, requirements, QA plan, CI/CD, deploy, GitHub settings — see `AGENTS.md` §8 map |
| Monorepo root | Submodule pointer bump, `docker-compose*.yaml`, `start-services.sh`, `.env.prod.example` |
| `.github/workflows/` | CI workflow change |
| `proxy/` | nginx config, local domain wiring |

If `ui/` and `api/` are both touched **and** the change is
contract-visible — also `openapi.json` regeneration **and** consumer
regeneration in `ui/`.

If `auth.md` is touched in either submodule — **both** must be
updated in the same scope of work (`AGENTS.md` §10).

### 3. Pick the right skills per area

| Area touched | Skill to load |
|---|---|
| `ui/` code | [`notebook-ui`](../notebook-ui/SKILL.md) + load `reatom` / `fractal-frontend` from `ui/.agents/skills/` as the task warrants |
| `api/` code | [`notebook-api`](../notebook-api/SKILL.md) (+ `references/liquibase-migrations.md` for DB, `references/openapi-sync.md` for contract changes) |
| Test design — pick level, map to qa-plan scenario | [`notebook-qa`](../notebook-qa/SKILL.md) |
| Verifying just-finished work is ready (before opening PR) | [`notebook-quality-analysis`](../notebook-quality-analysis/SKILL.md) |
| Drafting the PR text | [`merge-request-message`](../merge-request-message/SKILL.md) |
| Approving someone else's PR | [`notebook-pr-review`](../notebook-pr-review/SKILL.md) |

You almost always want at least `notebook-ui` **or** `notebook-api`.
For test design and scenario mapping — `notebook-qa`. For verifying
the work is ready before opening the PR — `notebook-quality-analysis`.
For the PR body — `merge-request-message`. Open the relevant
references only when their sub-topic comes up (don't preload).

### 4. Sequence the steps (push and PR order)

The fixed order, from `AGENTS.md` §7:

1. **Inside the submodule** that holds the contract or the deeper
   layer:
   - branch off `main`
   - implement
   - run local checks (`pytest` / `ruff` in `api/`;
     `pnpm test` / `lint` / `typecheck` in `ui/`)
   - commit + push to the submodule's remote
   - open a PR in the submodule repo, wait for CI, get review

2. **Inside the other submodule** (if both are touched), repeat the
   same flow. Order: **api first if it changes the contract**, ui
   second to consume it.

3. **In the monorepo**:
   - branch off `main`
   - bump the submodule pointer(s): `git add api ui` → commit
   - update any `/docs/*.md` whose logic changed (`AGENTS.md` §9)
   - update `AGENTS.md` itself if structure / stack / conventions
     changed
   - commit, push, open the monorepo PR

The monorepo PR cannot merge until **both** submodule PRs are
merged — a pointer to an open feature branch will be orphaned when
that branch rebases or gets squashed.

### 5. Plan the contract-sync edits

If the contract changes anywhere — plan the synchronous edits up
front.

**OpenAPI**:

- in `api/`: change the route / Pydantic schema → run
  `python scripts/openapi.py dump` → commit
  `api/docs/openapi.json` together with the route change
- in `ui/`: run `pnpm api:generate` → wire the call through
  `src/shared/api/<domain>.ts` (never direct `generated/` imports)
- See `notebook-api/references/openapi-sync.md` for the full flow.

**auth.md**:

- both `api/docs/auth.md` and `ui/docs/auth.md` must move together.
  The auth contract has the longest blast radius — a 1-sided edit
  silently misaligns the two sides for the next reader.
- See `AGENTS.md` §10.

**Other `/docs/*.md`**:

- Any document whose subject your change touches gets updated in
  the same PR. The map is in `AGENTS.md` §8.

### 6. Plan the verification

Before claiming the task done, the plan must include:

- Local checks: `pytest`, `pnpm test` / `pnpm lint` / `pnpm typecheck`
- CI checks expected to be green (note `paths` filters — see
  `docs/github-actions-pr-checks.md`)
- Manual browser verification for user-visible changes
  (`notebook-qa/references/manual-test-checklist.md`)
- QA scenarios from `docs/qa-plan.md` §6 covered or extended

### 7. Plan the PR description

Use `merge-request-message` skill to draft the description. The
template covers Problem / Solution / Verification / Known issues /
Screenshots / Notes / Closes. Output to
`.agents/pr-drafts/<branch>-pr.md` (gitignored), iterate with the
user, then post via `gh pr create`.

### 8. Output the plan

A planning output for this repo should answer, in order:

1. **Touched surfaces** — which submodules / docs / workflows.
2. **Skills to load** — which `.agents/skills/notebook-*` plus
   relevant references.
3. **Sequencing** — exact push and PR order across submodules and
   monorepo.
4. **Contract sync** — OpenAPI dump + ui regen, `auth.md` pair, any
   `/docs` updates.
5. **Verification** — commands to run, scenarios to walk through.
6. **PR text plan** — pointer to `merge-request-message`.
7. **Risks** — what could fail (orphaned pointer, drift, missing
   migration).

## Plan output template — lite (S-sized tasks)

For an S task that still benefits from a written plan (e.g. one
specialist + one doc update), use this short shape — the full
template below is overhead at this size.

```markdown
# Plan: <task name or ticket>

**Goal:** <one sentence — what behaviour exists after this is done>

**Surfaces:** <api / ui / docs / monorepo — which>

**Steps:**
1. <imperative — file or area>
2. <imperative — file or area>

**Verification:** <commands to run + one browser/cli check>

**Risks:** <1–2 lines — what's not obvious>
```

If any section grows past two lines, switch to the full template
below — that's the signal that the task isn't actually S.

## Plan output template — full

When producing a plan (e.g. in a chat reply, a `.agents/pr-drafts/`
note, or before kicking off implementation), use this shape. Omit
any section that genuinely has nothing in it.

```markdown
# Implementation plan: <task name or ticket>

## Goal
<Concise — what behaviour must exist after this is done. User /
system impact, not implementation.>

## Touched surfaces
- `api/`     <yes / no — why>
- `ui/`      <yes / no — why>
- `/docs/*`  <which files, per AGENTS.md §8 map>
- Monorepo root (compose, proxy, workflows)  <yes / no>

## Skills to load
- `notebook-<ui|api|qa|pr-review>` + relevant references
- `merge-request-message` for the PR description

## Sequencing
1. Inside <api/ui> — <what changes, push to submodule remote, PR>
2. Inside <other submodule, if any> — <what changes, push, PR>
3. Monorepo — pointer bump(s) + `/docs/*` updates + PR
   (only after submodule PRs are merged)

## Contract sync
- OpenAPI: <changes? if yes, `scripts/openapi.py dump` step, then
  `pnpm api:generate` on the ui side>
- `auth.md`: <touched? if yes, list both api/docs/auth.md and
  ui/docs/auth.md as paired edits>
- Other `/docs/*.md`: <list>

## Tasks

### T1 — <imperative title>
- **Acceptance**: <2–3 testable conditions>
- **Verification**: <commands to run / scenarios to walk>
- **Dependencies**: <Task numbers or "None">
- **Files**: <paths>
- **Size**: <XS / S / M / L>

### T2 — …

## Verification (whole task)
- Local: `pytest` / `pnpm test` / `pnpm lint` / `pnpm typecheck`
- CI: which workflows are expected green; which `Skipped` is expected
- Manual: `notebook-qa/references/manual-test-checklist.md` sections
  to walk
- QA scenarios from `docs/qa-plan.md` §6 covered / added

## PR text plan
Draft via `.agents/skills/merge-request-message`. Output at
`.agents/pr-drafts/<branch>-pr.md`.

## Risks
- <Risk → likely impact → mitigation>
- Typical: orphaned submodule pointer, OpenAPI drift, doc drift,
  forgotten `auth.md` pair, broken `paths`-filtered CI on docs-only PR

## Open questions
- <Question that needs an answer before / during implementation>
```

## Task sizing

Each task in the plan gets a size label. The label is a sanity
check — if everything is `L`/`XL`, the decomposition is wrong.

| Size | What it looks like |
|---|---|
| **XS** | Config tweak, copy / typo change, one small function, one log line. |
| **S** | One file or one isolated behaviour. Single test added. Small Liquibase changeset. |
| **M** | One coherent feature slice across a few files (typically inside one submodule). Single new endpoint + its consumer wiring. |
| **L** | Broad change — touches both submodules, includes a contract change + consumer, or a migration with backfill. Usually should be split unless the work is genuinely one unit. |
| **XL** | Too large to implement or review safely. Must be broken down before implementation starts. |

Aim for `S`–`M` tasks. `L` is acceptable for a single coherent unit
("rewrite auth module per `api/docs/auth.md` §5"); `XL` always
indicates re-planning is needed.

## Split triggers

A task should be split when **any** of these fire:

- **More than 3 acceptance criteria.** Either the scope is fuzzy or
  it's actually several tasks pretending to be one.
- **"And" in the title.** "Add OTP verification **and** refactor
  session storage" is two tasks. Promote the conjunction to the
  task boundary.
- **Touches unrelated subsystems in one task.** Adding a notebook
  field and fixing a CI workflow in the same task — split. The
  failure modes don't overlap.
- **Cannot be verified independently.** If a reviewer can't run the
  task's verification without the *next* task being done — split,
  or reorder the plan so verification is possible at each step.
- **Would leave the system broken until a later task.** Each task
  should leave `main` green (after squash-merge). If "part 2" is
  required just to make the test suite pass — they're one task, or
  the boundary is drawn wrong.
- **Spans both submodules + monorepo pointer bump.** Per `AGENTS.md`
  §7 push order, that's three commits across three repositories —
  it's at least three tasks, in the right order (api → ui →
  monorepo).
- **Crosses a contract boundary** (OpenAPI schema, `auth.md`,
  `notebooks.cells` shape) without listing the consumer-side updates
  as separate tasks. The contract change and the consumer migration
  are two units — split, with the contract first.

## Red flags

- **"Just commit to monorepo"** when the actual code lives in a
  submodule — the monorepo only points at submodule commits. Code
  changes must go to the submodule first.
- **Planning the monorepo PR before the submodule PRs are even
  open** — sequencing inversion. The monorepo PR is the **last**
  step.
- **"We'll dump OpenAPI later"** — the PR-time `bump --dry-run`
  check fails on stale `openapi.json`; the ui side cannot regenerate
  types correctly. Dump as part of the same submodule commit that
  changes the route.
- **Touching `auth.md` in one submodule** — the contract diverges
  silently. Always plan the paired edit.
- **A plan that doesn't mention any `/docs/*.md` for a feature
  task** — usually a sign the architecture/requirements/QA doc
  affected by the change wasn't checked.
- **A plan with one PR for everything** — three things at once
  (api change + ui consumer + monorepo bump) packaged as one
  monorepo PR is impossible by design (submodule PRs must merge
  first). If the plan implies that, it needs splitting.
- **Branching off a feature branch instead of `main`** — protection
  rules expect feature branches off `main`. Cross-branching is
  almost never what you want.

## Verification

A plan is ready when:

- [ ] Touched surfaces enumerated (api / ui / docs / workflows).
- [ ] Each surface has a named skill to load.
- [ ] Submodule PRs are ordered before the monorepo PR; contract
      side before consumer side.
- [ ] OpenAPI dump step is in the same submodule commit as the
      contract change (if applicable).
- [ ] `auth.md` pair is planned together (if auth touched).
- [ ] `/docs/*.md` updates are listed (`AGENTS.md` §8 map walked).
- [ ] Verification steps include local checks, CI expectations,
      and (for UI) manual browser check.
- [ ] PR description authoring step references
      `merge-request-message`.
- [ ] Risks called out — pointer orphan, OpenAPI drift, missing
      migration, doc drift.
- [ ] Each task has a size label (`XS`/`S`/`M`/`L`/`XL`) and no
      task is `XL`; `L` tasks have a stated reason for staying
      combined.
- [ ] No split-trigger condition fires for any task (>3 acceptance
      criteria, "and" in title, unrelated subsystems, can't verify
      independently, leaves system broken, crosses contract without
      separate consumer task).

## Related

**Primary** (read alongside this skill for any non-trivial task):

- `AGENTS.md` §2 (submodule structure), §7 (branch / PR / OpenAPI
  conventions), §8 (docs map), §9 (docs sync), §10 (`auth.md` sync)
- [`notebook-ui`](../notebook-ui/SKILL.md) — for ui-touching work
- [`notebook-api`](../notebook-api/SKILL.md) — for api-touching work
- [`notebook-llm`](../notebook-llm/SKILL.md) — additionally, when
  LLM proxy / WASM tier / prompt / API-key path is touched

**Secondary** (load only when the sub-topic comes up):

- [`notebook-api/references/openapi-sync.md`](../notebook-api/references/openapi-sync.md)
  — contract changes
- [`notebook-api/references/liquibase-migrations.md`](../notebook-api/references/liquibase-migrations.md)
  — DB schema changes
- [`notebook-qa`](../notebook-qa/SKILL.md) — test design (M+ tasks)
- [`notebook-qa/references/manual-test-checklist.md`](../notebook-qa/references/manual-test-checklist.md)
  — browser walk
- [`notebook-quality-analysis`](../notebook-quality-analysis/SKILL.md)
  — verifying just-finished work, before the PR opens
- [`merge-request-message`](../merge-request-message/SKILL.md) — at
  PR-authoring time
- [`notebook-pr-review`](../notebook-pr-review/SKILL.md) — when
  reviewing someone else's PR
- [`../rules/commit-message-rule.md`](../../rules/commit-message-rule.md)
  — commit subject patterns (the squash result on `main`)
- `docs/github-actions-pr-checks.md` — `paths` filters explain
  why a check might be `Skipped`
- `docs/github-repository-settings.md` — `main` protection rules,
  squash-merge default, conversation resolution requirement
