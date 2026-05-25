---
name: notebook-ui
description: >
  Project-specific guide for working inside the `ui/` submodule of JS
  Notebook — React 19 + Vite + pnpm, Reatom for state/routing/forms,
  fractal layers, HTTP through the @/shared/api facade. Load this
  skill whenever a task touches `ui/` code: new pages, features,
  components, state, HTTP calls, forms, routing, Vitest. Points at the
  deeper framework skills (reatom, fractal-frontend) and the task
  recipes in ui/.agents/.
globs:
  - "ui/**"
---

# notebook-ui

Top-level orientation for any work inside `ui/`. This skill is a router
— it tells you **which** specialised skill or doc to load next, and
enforces the few rules that are easy to miss if you default to generic
React/JS habits.

## Overview

`ui/` is the React 19 SPA of JS Notebook. It is a **git submodule** —
edits inside `ui/` need their own commit + push there, before the
monorepo bumps the pointer (see `AGENTS.md` §2, §7).

Stack (authoritative list in root `AGENTS.md` §3):

- React 19 + TypeScript, Vite, pnpm
- Reatom (`@reatom/core` + `@reatom/react`) — state, routing, forms
- Tailwind CSS + shadcn + Base UI
- openapi-fetch — HTTP types generated from the ui's own
  `ui/openapi/*.openapi.yaml` specs (hand-synced against the api's
  `api/docs/openapi.json` snapshot; see the HTTP rule below)
- Vitest + Testing Library, ESLint, lefthook

## Instruction priority

When this skill conflicts with `AGENTS.md`, the canonical docs under
`/docs`, or the submodule's own `ui/AGENTS.md` and
`ui/docs/architecture/*` — follow the project-specific source. This
skill is supplemental.

## When to use

Load this skill at the start of any task that edits files under `ui/`.
Stay loaded — it cross-links to:

- `ui/.agents/skills/reatom/SKILL.md` — load whenever state, async
  data, side effects, routing, or forms are involved
- `ui/.agents/skills/fractal-frontend/SKILL.md` — load whenever
  deciding **where** new code should live (which layer, which feature)
- `ui/.agents/<verb>-<noun>.md` recipes — load whichever matches the
  task (add a page, add a shadcn component, add an endpoint, etc.)

## Process

### 1. Read the entry doc

`ui/AGENTS.md` is the index of UI-specific conventions. Read it
first — it points at the architecture docs in `ui/docs/architecture/`
that are the source of truth for folder layout, routing, path
aliases, Reatom integration, and the HTTP layer.

### 2. Decide what kind of change it is, load the right skill

| Task | Load this |
|---|---|
| State, async data, side effects, event orchestration | `ui/.agents/skills/reatom/SKILL.md` |
| Routes (new route, params, loader, layout, protected) | `ui/.agents/skills/reatom/SKILL.md` (Routing section) |
| Forms | `ui/.agents/skills/reatom/SKILL.md` (Forms section) |
| Where to put new code (layer, feature, entity) | `ui/.agents/skills/fractal-frontend/SKILL.md` |
| Add a new page (route + sidebar) | `ui/.agents/add-page.md` |
| Add a shadcn primitive | `ui/.agents/add-shadcn.md` + `fix-shadcn-placement.md` |
| Build a new reusable component | `ui/.agents/add-custom-component.md` |
| Wire a new backend call | `ui/.agents/add-endpoint.md` + the **HTTP rule** below |
| Write a new doc under `ui/docs/` | `ui/.agents/add-doc.md` |

### 3. Apply the repo-specific rules

These are the rules a generic React habit will violate:

**Reatom + `clearStack()` — every async/event boundary needs `wrap`.**
`src/setup.ts` enables `clearStack()`. Consequence: every React event
handler that calls an atom or action must be wrapped, or it throws
`ReatomError: missing async stack` at runtime.

```tsx
// ✗ throws at click time
<button onClick={() => myAction()} />

// ✓
<button onClick={wrap(() => myAction())} />
```

If you see `missing async stack` in the console — that's this rule
firing. Read `ui/docs/architecture/reatom.md` before continuing.

**No `useState` / `useReducer` / `react-router` / hand-rolled forms.**
Use Reatom primitives: `atom`/`computed`/`action`, `reatomRoute`/
`urlAtom`, `reatomForm`/`reatomField`. The Reatom skill makes this a
directive, not a preference.

**HTTP only through `@/shared/api`.** Never import from
`@/shared/api/generated/**` in `features/`, `pages/`, or `app/` —
ESLint (`no-restricted-imports`) will fail the build. Adding an
endpoint:

1. Edit `ui/openapi/<domain>.openapi.yaml`. If the endpoint comes
   from an api contract change, **port it by hand** from the api's
   `api/docs/openapi.json` snapshot — there is no script that
   converts the api snapshot into these per-domain YAML specs, so the
   transfer is manual (mirror the changed path/schema/field).
2. Run `pnpm api:generate` (reads `ui/openapi/*.openapi.yaml`, writes
   `src/shared/api/generated/openapi-ts/<domain>.d.ts`)
3. Add a thin function to `src/shared/api/<domain>.ts`
4. Re-export from the facade

See `ui/docs/architecture/api-layer.md`,
`ui/.agents/add-endpoint.md`, and — for the api → ui contract flow —
`.agents/skills/notebook-api/references/openapi-sync.md`
("Cross-submodule sync").

**Fractal layer direction is strict.** `app → pages → widgets →
features → entities → shared`. Cross-feature imports are forbidden.
If you reach for one — the feature boundary is wrong; redraw rather
than work around. See `fractal-frontend` skill.

**Public API via `index.ts`.** Import from a module barrel, not its
internals. Exception: `shared/` has no barrel — direct file imports.

**Domain-based file naming.** `model/user.ts`, not `model/types.ts`.

### 4. Run the checks locally before pushing

```bash
cd ui
pnpm lint
pnpm typecheck
pnpm test
```

CI runs the same in `ui-ci.yml`. Failing them locally just delays the
loop.

### 5. Verify in the browser (UI changes)

Type-checking and Vitest verify code correctness, not feature
correctness. For any user-visible change, run the dev server and
exercise the feature in a real browser:

```bash
./start-services.sh   # or: docker compose up --build -d
# UI at http://notebook.com (see root AGENTS.md §4 for the hosts setup)
```

Check the golden path **and** an edge case. If you can't test the UI
manually for some reason, say so explicitly in the PR description —
do not claim success based on tests alone.

### 6. Push order (submodule discipline)

`ui/` is a submodule: commit + push inside `ui/` to its remote
**first**, then bump the monorepo pointer (`git add ui` → commit
→ push). Canonical rule in `AGENTS.md` §7. Skipping step 1 leaves
a monorepo pointer no one else can fetch.

## Red flags

- **`useState`, `useReducer`, or `useEffect` for fetching in new
  code** — wrong primitive. Read the `reatom` skill. Existing
  `useState` may live during a migration; new code should not.
- **`import { ... } from 'react-router-dom'`** — wrong primitive.
  Use `reatomRoute`/`urlAtom`.
- **`import { ... } from '@/shared/api/generated/...'` from a
  feature/page** — ESLint will fail. Go through the facade.
- **`import { Foo } from '@/features/B'` inside `features/A`** —
  cross-feature import forbidden (`fractal-frontend` §4).
- **`onClick={() => action()}` without `wrap`** — runtime crash at
  click time.
- **A feature folder named after a single use-case
  (`features/create-issue/`)** — features are cohesive product blocks,
  not single user actions (`fractal-frontend` §3, §7-7).
- **OpenAPI consumer types out of date** — after an api contract
  change, first **hand-port** the diff into the matching
  `ui/openapi/<domain>.openapi.yaml` (the api snapshot is not read
  directly), then run `pnpm api:generate`. `pnpm api:check` only
  catches YAML↔generated drift, not snapshot↔YAML drift. See
  `.agents/skills/notebook-api/references/openapi-sync.md`.

## Verification

Before marking a UI task done:

- [ ] `pnpm lint`, `pnpm typecheck`, `pnpm test` pass locally
- [ ] Feature exercised in the browser (golden path + at least one
      edge case); regressions in adjacent features checked
- [ ] No `missing async stack` errors in the console
- [ ] No `useState`/`react-router`/hand-rolled form added in new code
- [ ] HTTP additions go through `@/shared/api` facade only
- [ ] If routes changed — navigation and loader behaviour checked
- [ ] If `ui/docs/` describes anything this change affects — docs
      updated in the same PR (`AGENTS.md` §9)
- [ ] If `ui/docs/auth.md` touched — `api/docs/auth.md` updated in the
      same scope (`AGENTS.md` §10)
- [ ] Submodule commit pushed before monorepo pointer bump
      (`AGENTS.md` §7)

## Related

**Primary** (load alongside this skill):

- `ui/AGENTS.md` — UI conventions index
- `ui/docs/architecture/` — folder-structure, routing, path-aliases,
  reatom, api-layer
- `ui/.agents/skills/reatom/SKILL.md` — Reatom directive (load
  whenever state / async / routing / forms are involved)
- `ui/.agents/skills/fractal-frontend/SKILL.md` — layer/feature
  rules (load when deciding where new code lives)
- `AGENTS.md` §3 (stack), §5 (checks), §7 (submodules), §9 (docs
  sync), §10 (`auth.md` sync)

**Secondary** (load only when the sub-topic comes up):

- `ui/.agents/` — task recipes (add-page, add-endpoint, add-shadcn, …)
- `.agents/skills/notebook-api/SKILL.md` — backend side; load when
  this PR also touches the API contract
- `.agents/skills/notebook-llm/SKILL.md` — when the change touches
  the WASM LLM client, prompt builder, or `/llm/generate` consumer
- `.agents/skills/notebook-pr-review/SKILL.md` — review checklist
  used against the resulting PR (load at PR review time, not impl)
