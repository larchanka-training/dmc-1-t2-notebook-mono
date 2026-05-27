# Commit message rule

Descriptive — codifies the patterns that already coexist on `main`.
Reflects how the team actually writes commits today, not a forced
canonization.

> No commit-msg hook enforces this. The lefthook in `ui/` covers
> pre-commit (prettier/eslint) and pre-push (typecheck/api-check)
> only. Treat this document as the team's shared convention, not a
> hard gate.

## Universal rules (apply to every commit)

1. **Imperative mood** — "Add", "Fix", "Bump", "Описать", "Обновить".
   Not "Added"/"Fixing"/"Adds".
2. **Subject ≤ 72 chars** as a target. The repo has commits up to
   130+ chars; treat that as the upper bound a reader will tolerate,
   not the goal.
3. **Subject is one line.** No trailing dot.
4. **Language** — Russian or English, the author's choice. **Don't
   mix within a single commit** (subject in EN, body in RU is OK if
   the audience differs, but inside the body itself pick one).
5. **Body wrapped at ~72 chars**, blank line between subject and
   body. Bodies are optional but recommended when context isn't
   obvious from the diff. See `1445a8e` for a clean example.
6. **No `--amend` or force-push on published commits**
   (`AGENTS.md` §7). Add a new commit on top instead.
7. **No `--no-verify`** unless an emergency. Prefer
   `LEFTHOOK=0 git commit ...` (per `ui/lefthook.yml` header note)
   when you must bypass — and explain why in the body.

## Accepted subject patterns

All three coexist on `main`. Pick whichever fits the work. No
hierarchy between them.

### 1. Ticketed: `TARDIS-NN: <subject>`

Use when the work has a tracker ticket. Most common pattern.

```
TARDIS-15: Bump api and ui submodules to merged auth docs
TARDIS-15: Mirror tombstones contract from api review
TARDIS-15: Address auth doc review feedback
```

For team-scope tasks without a specific ticket number, the longer
form is also accepted:

```
TARDIS: T2: DevOps: Описать repository rules и required checks
TARDIS: T2: DevOps: Обновить GitHub Actions под Node.js 24
```

Cap the long form before it bloats — `TARDIS: T2: Engineer — Backend
Foundation: <very long subject>` is a historical example, not a
target.

### 2. Conventional Commits: `<type>(<scope>): <subject>`

Used heavily in the `ui/` submodule and for chore/docs/refactor in
the monorepo. Lowercase `type`.

```
feat(api): scaffold OpenAPI codegen, shared/api facade, MSW dev mocks
fix(shadcn): update components.json aliases to fractal structure
refactor(ci): rework PR workflow, drop MSW, wire vitest coverage
docs(api): api-layer, folder-structure update, add-endpoint skill
chore: bump ui submodule
chore(openapi): bump version to 0.1.1 [skip ci]
```

Common `type`s observed: `feat`, `fix`, `refactor`, `docs`, `chore`,
`test`. Scope (in parens) is optional and usually names the module
(`api`, `ui`, `shadcn`, `entities`, `ci`, `openapi`).

> A capital-D `Docs:` is also out there in the wild (`Docs: убрать
> личные recommendation notes`). Prefer lowercase to keep the type
> tag scannable.

### 3. Plain imperative subject

For monorepo housekeeping without a ticket — older commits are full
of this style. Still accepted, but the two patterns above are
clearer for new work.

```
Подготовить production compose для GHCR images
Добавить multi-arch публикацию Docker images
Обновить локальный запуск сервисов с учетом pnpm
```

## Body conventions

Optional, but write one when:

- The diff isn't self-explanatory (cross-module impact, non-obvious
  rationale, deferred follow-ups)
- The PR description doesn't already carry the context (post-squash
  the body **becomes** the only context on `main`)

When you write a body:

- Blank line between subject and body.
- Wrap at ~72 chars.
- Bullet list is fine — see `1445a8e`:

  ```
  docs: перевести проектную документацию на английский

  Перевод всех документов из карты документации AGENTS.md §8 на
  английский — единый язык docs/ для агентов и разработчиков:

  - System_Architecture.md, requirements.md, project.md,
    backend-recommendations.md
  - qa-plan.md, autotest-tasks.md
  - ci-cd.md, deploy.md, github-actions-pr-checks.md,
    github-repository-settings.md, Local-Proxy.md

  execution-architecture.md и AGENTS.md уже на английском (PR #58).
  ```

- Use trailers (`Closes #NN`, `Refs <owner/repo>#NN`,
  `Refs TARDIS-NN`, `Co-Authored-By:`) at the end, separated by a
  blank line.
  - `Closes #NN` — same-repo issue; GitHub auto-closes on merge.
  - `Refs larchanka-training/dmc-1-t2-notebook-mono#NN` — issue in
    a different repo (typical: submodule PR referencing a monorepo
    issue). Use the full `owner/repo#NN` form so the link
    resolves; GitHub does **not** auto-close cross-repo. Close the
    issue from the monorepo PR instead.
  - `Refs TARDIS-NN` — tracker-only ticket without a GitHub issue.
    Plain text, not clickable, but documents the tracker.

## Submodule pointer bumps

In the monorepo, a commit that only bumps a submodule pointer
follows one of these patterns, in order of preference:

```
TARDIS-NN: Bump <api|ui> submodule to <short context>      # ticketed
chore: bump <api|ui> submodule                              # routine
Обновить <api|ui> submodule после <reason>                  # legacy plain
```

The body **should** name the included submodule PRs (`#NN` in the
submodule repo) and the most important changes pulled in. A bare
`chore: bump ui submodule` with no body is the bare minimum — fine
for genuinely routine bumps (`docstring cleanup`), thin for anything
substantial.

Dependabot generates `Bump <package> from <a> to <b>` automatically;
do not edit those into another pattern.

## Squash-merge behaviour

The repo's default merge strategy is **squash merge**
(`docs/github-repository-settings.md`). The practical effect on
`main`:

- The PR title becomes the squash commit subject.
- GitHub appends ` (#NN)` to that subject (the PR number).
- The PR body becomes the squash commit body.

So:

- **Write the PR title like a subject**: imperative mood, ≤ 72 chars,
  one of the patterns above. **Don't** lead the PR title with
  `Draft:` if you intend to merge as-is — strip the `Draft:` prefix
  before merging (the GitHub draft state replaces it).
- **Write the PR body like a commit body**: the squash result is the
  only thing `git log` shows on `main`.

In the submodule histories before squash, feature branches commonly
have `wip` and small fix-up commits. That's expected — they vanish
on squash. Just don't merge a feature branch into `main` without
squashing.

## What to avoid

- **Junk subjects.** `wip`, `fix`, `update`, `temp`. Acceptable on a
  feature branch in flight; never in a squash-merge result.
- **Generated subjects.** `Update files via Codespaces`. Edit before
  merging.
- **Punctuation noise.** `Add\nfeature` (literal `\n`), trailing
  ellipsis, multiple exclamation marks.
- **Mixing patterns within one subject.** `feat: TARDIS-15: …` is
  not a thing — pick one (use a `Refs TARDIS-15` trailer in the body
  instead).
- **Capitalised type tag.** `Feat:`, `Docs:`, `Chore:` — lowercase
  is the convention.
- **Force-push or `--amend` after the commit is published**
  (`AGENTS.md` §7).
- **`--no-verify`** without explicit reason. Prefer `LEFTHOOK=0` for
  bypassing pre-commit/pre-push and document the bypass.

## Examples — real history

Good (clear what changed, scoped, scannable):

```
TARDIS-15: Bump api and ui submodules to merged auth docs
feat(api): scaffold OpenAPI codegen, shared/api facade, MSW dev mocks
refactor(ci): rework PR workflow, drop MSW, wire vitest coverage
chore: bump ui submodule
docs: перевести проектную документацию на английский
```

Less good (too long / unclear / stale style — don't copy):

```
TARDIS: T2: Engineer — Backend Foundation: добавление Swagger
документация, config, logging, API-версионирование, продумать
и миграция            # 130+ chars, "продумать" leaks intent
wip                   # ok on feature branch, never squash like this
Add UI CI and Docker compose setup    # would be cleaner as feat(ci): …
```

## Cross-link

- `AGENTS.md` §7 — branch/PR/git-history conventions (no amend, no
  force-push on published commits, no direct push to `main`)
- `docs/github-repository-settings.md` — squash-merge default,
  branch protection, PR title implications
- `.agents/skills/merge-request-message/SKILL.md` — generates PR
  descriptions; the PR title flows directly into the squash subject
- `ui/lefthook.yml` — pre-commit/pre-push hooks (no commit-msg
  enforcement at this layer)
