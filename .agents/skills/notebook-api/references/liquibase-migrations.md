# Liquibase migrations

Load this reference when adding or changing the database schema in
`api/`. Liquibase — not Alembic — is the migration tool in this
project (even though `docs/backend-recommendations.md` mentions
Alembic; that doc predates the decision).

## Where things live

```text
api/liquibase/
├── changelog/
│   ├── changelog-master.xml          # entry point; includes per-module changesets
│   └── changes/                      # per-module changeset files
└── liquibase.properties              # connection + driver config
```

The convention is **one changeset file per module** (or per logical
slice), included from `changelog-master.xml`. Don't put unrelated
changes in the same file.

## Adding a changeset

1. Create the changeset file under
   `liquibase/changelog/changes/<module>-<NN>-<short-slug>.xml`.
   `<NN>` is a zero-padded ordinal within the module (`auth-01-…`,
   `auth-02-…`).
2. Inside the file use `<changeSet id="…" author="…">`. The `id` is
   immutable once the changeset has been applied anywhere — Liquibase
   identifies applied changes by `(id, author, file)` triple.
3. Add an `<include file="…" />` line to `changelog-master.xml`,
   keeping the order **append-only**. Never reorder applied entries.
4. Prefer the XML form for simple DDL (`createTable`, `addColumn`)
   because Liquibase generates the rollback automatically. Use raw
   `<sql>` only when no built-in operation fits, and pair it with an
   explicit `<rollback>` block.

## Rules

- **Append-only.** Once a changeset has been applied (locally, in CI,
  or in any environment) — never edit it. Add a new changeset that
  corrects course.
- **No DDL from app code.** Schema mutations belong in Liquibase, not
  in startup hooks. The app should be able to boot against a fully
  pre-migrated database.
- **One concern per changeset.** Easier to roll back; easier to
  bisect when something goes wrong.
- **Explicit constraints.** Name your constraints (`fk_…`, `idx_…`,
  `uq_…`) — generated names differ between Postgres versions and make
  diffs noisy.
- **Backfill with care.** A `NOT NULL` column on an existing table
  needs a default or a backfill step in a separate changeset before
  the constraint flips.

## Running migrations

Locally — Liquibase is invoked from the container or via a CLI script
(check `api/liquibase/liquibase.properties` for the current target
URL and driver). The app does **not** apply migrations on boot for
this project — they are applied as a separate step (in CI, in deploy,
or on demand).

## Rollback strategy

- Built-in DDL → Liquibase generates rollback automatically; no work
  needed.
- `<sql>` → write `<rollback><sql>…</sql></rollback>` explicitly.
- Data-only changesets that can't be rolled back → add
  `<rollback><empty/></rollback>` and document the irreversibility in
  the PR description.

## Cross-link

- `api/README.md` — "How to add a new module" step 4 (add a per-module
  changeset)
- `api/docs/auth.md` §4 — the auth-related target schema (`users`,
  `otps`, `sessions`, `refresh_tokens`, `notebooks`) — when the auth
  module is implemented, its changesets should match this shape
- `.agents/skills/notebook-api/SKILL.md` — process step 4 ("Database
  changes — always Liquibase")
