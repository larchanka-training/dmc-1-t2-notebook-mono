# OpenAPI sync (api → ui)

Load this reference when an api change is visible at the HTTP
contract: new endpoint, new schema, new field, removed field,
renamed schema, response code, required-flag flip. Skip if the
change is purely internal (refactor, log line, test).

## The contract surface

- `api/docs/openapi.json` — the committed snapshot. **This is the
  authoritative description of the api contract.** For **auth/llm**, the
  ui keeps its own per-domain specs that a human syncs against this
  snapshot (see "Cross-submodule sync" below). For **notebook**, the ui
  vendors a copy of this snapshot and generates from it — no hand-port.
- The running app generates its OpenAPI live from the FastAPI route
  definitions and Pydantic schemas (`/openapi.json`).
- The snapshot in the repo must match what the running app would
  produce. Drift between them = CI failure.

## The tooling

These commands run **from inside the `api/` submodule** (cwd =
`.../api`), where `scripts/openapi.py` lives. From the monorepo
root, prefix with `api/` (e.g. `python api/scripts/openapi.py dump`)
or use `git -C api ...` for the staging step.

```bash
# Refresh the committed snapshot from the running app
python scripts/openapi.py dump

# Detect drift and decide whether to bump the version (semver)
python scripts/openapi.py bump            # writes pyproject.toml + snapshot
python scripts/openapi.py bump --dry-run  # report only (used in CI)
```

`bump` applies semver rules:

| Kind  | Trigger                                                        |
| ----- | -------------------------------------------------------------- |
| MAJOR | Removed path **or** added/removed `required` field on a schema |
| MINOR | New path added                                                 |
| PATCH | Anything else (descriptions, examples, response tweaks)        |

## Automation

The workflow lives **inside the api repo**:
`.github/workflows/openapi-version.yml` (i.e.
`api/.github/workflows/openapi-version.yml` from the monorepo root) —
not in the monorepo's own `.github/`.

- **On PR**: runs `bump --dry-run`. If the snapshot
  (`docs/openapi.json` inside api) is stale (or `pyproject.toml`
  version is out of step) — the check fails. The fix is to run
  `dump` locally and commit the diff.
- **On push to `main`**: runs `bump`, commits the updated
  `pyproject.toml` + `docs/openapi.json`, tags the commit
  `vX.Y.Z`, pushes the tag.

The tag triggers the api repo's `.github/workflows/docker-publish.yml`
to publish a GHCR image with tags `{{version}}` and
`{{major}}.{{minor}}`. So a Swagger-visible change automatically
becomes a new image — no manual release step.

## When to dump

Always after:

- Adding or removing an endpoint
- Renaming a path
- Adding, renaming, or removing a Pydantic field on a request/response
  schema
- Flipping a field's `required` flag
- Changing a response status code
- Changing the OpenAPI metadata in `app/main.py`

Never (no dump needed):

- Pure refactors that don't change route definitions or schemas
- Test changes
- Log messages, docstrings inside Python code (vs. FastAPI
  `description=`/`summary=`, which **does** show in the schema)

If unsure — run `bump --dry-run`; if it reports drift, dump.

## Cross-submodule sync (api ↔ ui)

**There is no automated bridge from `api/docs/openapi.json` to the
ui.** The two sides hold *different* artifacts:

- api side: `api/docs/openapi.json` — one whole-app snapshot, dumped
  from FastAPI by `scripts/openapi.py`.
- ui side, **auth/llm**: `ui/openapi/<domain>.openapi.yaml` (today:
  `auth.openapi.yaml`, `llm.openapi.yaml`) — hand-maintained,
  **per-domain** specs. `pnpm api:generate` (`ui/scripts/api-gen.mjs`)
  reads *these YAML files*, not the api snapshot.
- ui side, **notebook**: `ui/openapi/backend/openapi.json` — a vendored
  machine copy of the api snapshot, refreshed by `pnpm api:vendor`.
  `pnpm api:generate` slices the `/api/v1/notebooks` paths out of it.

Both write `ui/src/shared/api/generated/openapi-ts/<domain>.d.ts`.

For **auth/llm**, no script copies or converts JSON → YAML. **A human
transfers the contract change** from the api snapshot into the relevant
`ui/openapi/<domain>.openapi.yaml` by hand (matching the changed
path/schema/field), then regenerates — manual and easy to forget. For
**notebook**, `pnpm api:vendor` copies the whole snapshot, so the
transfer is mechanical (no per-field porting).

So a contract change is a **two-submodule** edit:

1. In `api/` — change route/schema → `python scripts/openapi.py dump`
   → commit + push the api submodule. `api/docs/openapi.json` now
   reflects the new contract.
2. In `ui/`:
   - **notebook** — `pnpm api:vendor` (refresh
     `ui/openapi/backend/openapi.json`) → `pnpm api:generate`.
   - **auth/llm** — **manually port the change** into the matching
     `ui/openapi/<domain>.openapi.yaml` → `pnpm api:generate`.

   Then write/adjust the thin facade in `src/shared/api/<domain>.ts` →
   commit + push the ui submodule.
3. In the monorepo — bump both submodule pointers in a single commit

For **auth/llm**, if you skip the manual port in step 2, `pnpm
api:generate` regenerates types from the **stale** YAML — no error, but
the ui ships types that don't match the server. `pnpm api:check` only
catches YAML-vs-generated drift, not YAML-vs-api-snapshot drift, so it
won't save you. For **notebook**, the analogous gap is forgetting
`pnpm api:vendor` (vendored copy vs live `api/docs/openapi.json`); a
cross-repo freshness check is a deferred follow-up.

## Red flags

- **PR fails on `OpenAPI Version / dry-run`** — `api/docs/openapi.json`
  is stale. Run `dump` and commit.
- **Manual edits to `api/docs/openapi.json`** — the file is generated.
  Edit the FastAPI route or Pydantic schema and re-dump.
- **ui PR consumes a schema field that doesn't exist in the snapshot
  on `main`** — the api change wasn't merged yet, or the ui side
  didn't regenerate. Resync.
- **`pyproject.toml` version moved without a snapshot change** —
  someone edited the version manually. `bump` is the only sanctioned
  way to move it.

## Cross-link

- `api/README.md` § "OpenAPI-driven versioning" — the canonical
  description of the workflow
- `ui/docs/architecture/api-layer.md` — how the ui consumes the
  generated types via the `@/shared/api` facade
- `ui/.agents/add-endpoint.md` — the ui-side recipe for wiring a new
  endpoint into the facade
- `.agents/skills/notebook-api/SKILL.md` — process step 5
- `.agents/skills/notebook-ui/SKILL.md` — "HTTP only through
  `@/shared/api`" rule
- `AGENTS.md` §7 — "When the backend API changes, update
  `api/docs/openapi.json` … notebook via `pnpm api:vendor` +
  `pnpm api:generate`; auth/llm hand-ported into
  `ui/openapi/<domain>.openapi.yaml`"
