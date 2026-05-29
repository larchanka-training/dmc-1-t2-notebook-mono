---
name: notebook-api
description: >
  Project-specific guide for working inside the `api/` submodule of JS
  Notebook — Python 3.12 + FastAPI on a versioned `/api/v1`,
  SQLAlchemy 2.0 + PostgreSQL 16, Liquibase migrations, JWT (HS256) +
  email OTP auth, structlog, pytest. Modular layout
  `app/modules/<module>/{controllers,services,schemas}/`. Load this
  skill whenever a task touches `api/` code: endpoints, models,
  migrations, auth, OpenAPI dump → ui sync, pytest.
globs:
  - "api/**"
---

# notebook-api

Top-level orientation for any work inside `api/`. Routes the task to
the right files, the right tooling (Liquibase, OpenAPI dump, pytest),
and the right cross-submodule contracts (OpenAPI → ui types,
`auth.md` sync).

## Overview

`api/` is the Python 3.12 + FastAPI backend of JS Notebook. It is a
**git submodule** — edits inside `api/` need their own commit + push
there, before the monorepo bumps the pointer (see `AGENTS.md` §2, §7).

Stack (authoritative list in root `AGENTS.md` §3 and
`api/README.md`):

- **Python 3.12**, **FastAPI** on versioned `/api/v1`
- **SQLAlchemy 2.0**, **PostgreSQL 16**, **Liquibase** for migrations
  (see [`references/liquibase-migrations.md`](./references/liquibase-migrations.md))
- **JWT (HS256)** access (15 min) + opaque refresh token (30 days) +
  email OTP sign-in — target model in `api/docs/auth.md` (the current
  `/auth/login` password endpoint is a temporary stub, see auth.md §1)
- **structlog** — JSON-ready logging
- **pytest** — integration tests via `TestClient`; `app.dependency_overrides`
  is the standard way to stub deps (e.g. `get_db`)
- **OpenAPI** snapshot at `api/docs/openapi.json` — source of truth for
  the ui's generated types (see
  [`references/openapi-sync.md`](./references/openapi-sync.md))

## Module layout

The repo is **multi-module**. Each domain module owns its slice:

```text
app/
├── core/
│   ├── config.py      # Pydantic settings (env-driven)
│   ├── db.py          # SQLAlchemy engine + get_db dependency
│   └── logging.py     # structlog config
├── modules/
│   └── <module>/
│       ├── __init__.py        # re-exports `router`
│       ├── controllers/       # HTTP endpoints (FastAPI APIRouter)
│       ├── services/          # business logic
│       └── schemas/           # Pydantic request/response DTOs
└── main.py            # FastAPI app + router includes
```

Only `health` exists today (`/health`, `/health/ready`). Auth,
notebooks, sync, llm — to be added per `api/docs/auth.md` and
`docs/backend-recommendations.md`.

> Note: `docs/backend-recommendations.md` was authored before the
> auth design was finalised — it mentions password + Alembic. The
> **actual** state is **OTP + Liquibase**, codified in
> `api/docs/auth.md` and `api/README.md`. Prefer those when they
> disagree.

## Instruction priority

When this skill conflicts with `AGENTS.md`, the canonical docs under
`/docs`, or the submodule's own `api/AGENTS.md`, `api/README.md`,
and `api/docs/*` — follow the project-specific source. This skill is
supplemental.

## When to use

Load this skill at the start of any task that edits files under
`api/`. Reach for the references on demand:

- [`references/liquibase-migrations.md`](./references/liquibase-migrations.md)
  — adding or changing DB schema
- [`references/openapi-sync.md`](./references/openapi-sync.md)
  — any change visible in the API contract (new path, new field, new
  response code, schema rename)

## Process

### 1. Read the entry docs

- `api/README.md` — module layout, OpenAPI tooling, "How to add a new
  module" recipe
- `api/docs/auth.md` — the target auth model (OTP → JWT + refresh
  rotation, sessions, refresh_tokens family, reuse-detection). This
  is the single source of truth for auth shape.

### 2. Decide the change type, route to the right tool

| Task | First steps |
|---|---|
| New endpoint on existing module | Add controller in `app/modules/<module>/controllers/`, schema in `schemas/`, service in `services/`. Wire in `__init__.py` router. Run `python scripts/openapi.py dump` after — see [openapi-sync](./references/openapi-sync.md) |
| New module | Follow `api/README.md` "How to add a new module" (skeleton + `app.include_router` + Liquibase changeset + tests). Run `openapi.py dump` |
| DB schema change | New Liquibase changeset — see [liquibase-migrations](./references/liquibase-migrations.md). **Do not** add an ad-hoc Alembic migration; this project uses Liquibase |
| Auth change | Read `api/docs/auth.md` first — the contract is detailed and tight. Any change here is a cross-submodule edit: `ui/docs/auth.md` must be updated in the same scope (`AGENTS.md` §10) |
| Notebook persistence / sync | Per-cell LWW + request-only tombstones is the agreed model (`auth.md` §7–§8). Don't reinvent — read those sections |
| LLM proxy | API keys must never reach the browser. Provider abstraction sits server-side; the ui calls a single endpoint |
| Health probe | `health` already exists. Add components to the readiness probe via the existing aggregator, don't add new endpoints |

### 3. Stick to the modular layout

- One router per module, re-exported from `__init__.py`.
- Module name = domain noun (`notebooks`, `auth`, `llm`). Not
  technical (`utils`, `helpers`).
- Cross-module dependencies go through `services/` interfaces, not
  by reaching into another module's `controllers/`.
- `core/` is for project-wide plumbing (config, db, logging) — not
  for business logic. Don't grow it ad hoc.

### 4. Database changes — always Liquibase

Add a per-module changeset under `liquibase/changelog/changes/` and
include it from `changelog-master.xml`. **No** raw SQL outside a
changeset; **no** schema mutations from app startup. Full procedure:
[`references/liquibase-migrations.md`](./references/liquibase-migrations.md).

### 5. API contract changes — dump OpenAPI

Any change visible at the API boundary (new path, new field, removed
field, renamed schema, response code, required-flag flip) requires a
dump + commit. Paths are relative to cwd — `openapi.py` lives in the
api repo, so the snapshot path is `docs/openapi.json` **from inside
`api/`**, not `api/docs/openapi.json`:

```bash
# from inside the api/ submodule (cwd = .../api):
python scripts/openapi.py dump
git add docs/openapi.json

# or from the monorepo root (cwd = .../dmc-1-t2-notebook-mono):
python api/scripts/openapi.py dump
git -C api add docs/openapi.json
```

The PR-time check `bump --dry-run` (CI workflow inside the api repo:
`.github/workflows/openapi-version.yml`, i.e.
`api/.github/workflows/openapi-version.yml` from the monorepo root)
fails when the snapshot is stale. The auto-bump on main commits the
new version + tag → triggers docker-publish. Details and semver
rules: [`references/openapi-sync.md`](./references/openapi-sync.md).

If the contract change is visible to the ui — the **ui PR** must also
land (in the same scope of work). The ui does **not** read this
snapshot directly: hand-port the diff into the matching
`ui/openapi/<domain>.openapi.yaml`, then run `pnpm api:generate` and
make any type-level fixups. The ui's `@/shared/api` facade is the
only place allowed to import from generated types. Full flow:
[`references/openapi-sync.md`](./references/openapi-sync.md)
"Cross-submodule sync".

### 6. Tests — pytest with dependency_overrides

The reference integration suite is `tests/test_startup.py`: boot the
app via `TestClient`, override `get_db` (and other dependencies) to
stub external resources. New modules should add their own
`tests/test_<module>.py` following the same pattern.

```bash
cd api
pytest                    # full suite
pytest tests/test_auth.py # one file
```

Don't reach for a real Postgres for unit-level tests — override the
`get_db` dependency. Integration tests that genuinely need Postgres
should use `TestContainers` and be marked, not run by default.

### 7. Lint

```bash
cd api
ruff check .
```

CI runs the same in `api-ci.yml`. Failing it locally just delays the
loop.

### 8. Push order (submodule discipline)

`api/` is a submodule: commit + push inside `api/` to its remote
**first**, then bump the monorepo pointer (`git add api` → commit
→ push). Canonical rule in `AGENTS.md` §7. Skipping step 1 leaves
a monorepo pointer no one else can fetch.

## Red flags

- **A schema change without a Liquibase changeset** — startup will
  drift between developers, prod will diverge from dev. See
  [liquibase-migrations](./references/liquibase-migrations.md).
- **An API change without `openapi.py dump`** — PR CI's
  `openapi bump --dry-run` will fail, and even if it didn't, the ui
  is now coupled to types that don't match the server. See
  [openapi-sync](./references/openapi-sync.md).
- **A new module that doesn't follow `app/modules/<name>/{controllers,services,schemas}/`**
  — the project's modular convention is intentional. Don't flatten or
  reorganise without a stated reason.
- **A migration that uses `app.dependency_overrides` outside tests**
  — overrides are a test affordance, not a runtime config switch.
- **Touching `auth.md` only on the backend side** — the contract is
  documented in two places (`api/docs/auth.md` and `ui/docs/auth.md`)
  and they must not diverge (`AGENTS.md` §10).
- **`oauth_name_*` or `token_ttl_seconds=86400` in `core/config.py`**
  — these are residual from the old design. The target is the env
  table in `api/docs/auth.md` §12 (`JWT_ACCESS_TTL_SECONDS=900`,
  `JWT_REFRESH_TTL_SECONDS=2592000`, etc.). Migrate, don't extend.
- **Returning the OTP code in `prod` mode** — `api/docs/auth.md` §6
  treats this as a defence-in-depth bug. The handler must branch on
  `APP_ENV` and the test that locks this behaviour must exist.

## Verification

Before marking an api task done:

- [ ] `ruff check .` clean
- [ ] `pytest` green; any new module has its own `tests/test_<module>.py`
- [ ] DB changes ship as a Liquibase changeset, not raw SQL or ORM
      side effect
- [ ] `python scripts/openapi.py dump` run if the contract changed;
      `api/docs/openapi.json` committed
- [ ] If the ui consumes the new contract — the ui PR is staged with
      `pnpm api:generate` (`AGENTS.md` §7 OpenAPI rule)
- [ ] If `api/docs/auth.md` touched — `ui/docs/auth.md` updated in
      the same scope (`AGENTS.md` §10)
- [ ] If `api/docs/` describes anything this change affects — docs
      updated in the same PR (`AGENTS.md` §9)
- [ ] Submodule commit pushed before monorepo pointer bump
      (`AGENTS.md` §7)
- [ ] No secrets (LLM keys, JWT secrets) leaked into responses, logs,
      or test fixtures

## Related

**Primary** (load alongside this skill):

- `api/README.md` — module layout + OpenAPI tooling
- `api/docs/auth.md` — target auth model + persistence + conflict
  resolution + versioning
- `AGENTS.md` §3 (stack), §5 (checks), §7 (submodules + OpenAPI), §9
  (docs sync), §10 (`auth.md` sync)

**Secondary** (load only when the sub-topic comes up):

- [`references/liquibase-migrations.md`](./references/liquibase-migrations.md)
  — DB schema changes
- [`references/openapi-sync.md`](./references/openapi-sync.md) —
  contract changes
- `docs/backend-recommendations.md` — historical context for stack
  choices (be aware it predates the OTP/Liquibase decisions; prefer
  `api/README.md` and `auth.md` when they disagree)
- `docs/System_Architecture.md` — system view (backend role,
  data flows)
- `docs/execution-architecture.md` — code execution model (frontend
  QuickJS is MVP; backend execution worker is the future path)
- `.agents/skills/notebook-ui/SKILL.md` — the ui side; load when the
  PR also touches the API contract
- `.agents/skills/notebook-llm/SKILL.md` — when the change touches
  the LLM proxy, prompt builder, rate limit, or provider abstraction
- `.agents/skills/notebook-pr-review/SKILL.md` — review checklist
  used against the resulting PR (load at PR review time, not impl)
