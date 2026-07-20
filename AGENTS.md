# AGENTS.md — JS Notebook (monorepo)

A document for AI agents and new developers: what this project is, how it is
structured, what it is built with, and how it is run and deployed. Details
live in the related documents under `/docs` (links at the end).

---

## 1. About the project

**JS Notebook** is a Jupyter-style web application for JavaScript/TypeScript.
A user builds notebooks out of cells of two types — **code** (JS/TS) and
**text** (Markdown) — runs the code and sees the output below the cell.

Key properties:

- **Hybrid code execution.** QuickJS/WASM in the browser is the MVP path for
  the current sprint; routing resource-heavy runs (or clients with ≤ 4 GB RAM)
  to the backend is the target/future extension. See
  [`docs/execution-architecture.md`](docs/execution-architecture.md).
- **Offline mode.** Notebooks autosave locally to IndexedDB as you type; once
  signed in, edits also push to the server automatically in the background
  (autosync, see `ui` remoteSync #134) and load back on sign-in. A status
  indicator shows where each save is — there is no manual "sync" button.
- **Accounts.** Sign-in via email + one-time code (OTP), no passwords; syncing
  notebooks requires being signed in.
- **LLM code generation.** A text description becomes code, through a backend
  proxy (API keys never leave the server).

Purpose — an educational SaaS project (Modern Software Development course),
team **T2**.

> **Quality bar — production-grade, within reasonable bounds.** Although this is
> a learning project, write code, infrastructure and docs as you would for
> production: correctness, security, clarity, and no throwaway shortcuts left in
> `main`. At the same time, scope to the realities of an educational project on a
> shared course account — deliberate, documented trade-offs are fine (e.g. bare
> HTTP without a domain/TLS for now, a single `production` environment with no
> staging, cost-conscious AWS choices). Rule of thumb: **production quality of
> execution, educational scope of ambition.** When you take such a shortcut, note
> it (in the relevant doc or as a follow-up) rather than hiding it.

---

## 2. Monorepo structure

The `dmc-1-t2-notebook-mono` monorepo orchestrates everything via Docker
Compose and contains two **git submodules**:

```
dmc-1-t2-notebook-mono/
├── AGENTS.md                 # this file
├── api/                      # submodule → dmc-1-t2-notebook-api  (backend)
├── ui/                       # submodule → dmc-1-t2-notebook-ui   (frontend)
├── docs/                     # project documentation (see section 8)
├── proxy/                    # nginx reverse-proxy (dev + prod configs)
├── terraform/                # AWS infrastructure (ARCHIVED reference — prod moved to Beget)
├── archive/aws-workflows/    # retired AWS CI/CD workflows (reference)
├── docker-compose.yaml       # local development (build from source)
├── docker-compose.prod.yaml  # production (prebuilt images from GHCR, runs on the Beget VPS)
├── docker-compose.autotests.yml # containerized autotest overlay (see autotests/)
├── .env.prod.example         # production environment template
├── start-services.sh         # quick local start
├── qa/                       # manual test cases (TC-*, by area)
├── autotests/                # standalone E2E (Playwright) + API (pytest) + Allure
└── .github/workflows/        # CI/CD (see section 6)
```

**Important about submodules:** `api` and `ui` are separate repositories.
A change in a submodule takes two steps: (1) commit + push inside the
submodule, (2) in the monorepo, update the pointer (`git add <submodule>` +
commit). Each submodule has its own `AGENTS.md`/`CLAUDE.md` — when working
inside `api/` or `ui/`, follow those.

| Submodule | Purpose | Documentation |
|---|---|---|
| `api` | Backend API (FastAPI) | `api/README.md`, `api/docs/` |
| `ui` | Frontend SPA (React) | `ui/README.md`, `ui/AGENTS.md`, `ui/docs/` |

---

## 3. Tech stack

### Backend (`api/`)
- **Python 3.12**, **FastAPI** — a versioned API (`/api/v1`)
- **SQLAlchemy 2.0** (ORM), **PostgreSQL 16**, migrations — **Liquibase**
- **structlog** — structured JSON logging
- Authentication — **JWT** (`HS256`) access token + **email OTP** sign-in
  (passwordless)
- Tests — **pytest**
- Modular architecture: `app/modules/<module>/{controllers,services,schemas}/`
- The OpenAPI schema is versioned (`scripts/openapi.py`, `docs/openapi.json`)

### Frontend (`ui/`)
- **React 19** + **TypeScript**, bundler — **Vite**, packages — **pnpm**
- State — **Reatom**; UI — **Tailwind CSS** + **shadcn** + **Base UI**
- HTTP client — **openapi-fetch** (types are generated from the api OpenAPI
  schema)
- Tests — **Vitest** + Testing Library; lint — ESLint; hooks — lefthook

### Infrastructure
- **Docker / Docker Compose** — orchestration of all services
- **nginx** — reverse-proxy (local domains `notebook.com` and subdomains)
- **PostgreSQL 16** + **pgAdmin** (locally)
- **GitHub Actions** — CI/CD; images are published to **GHCR**
  (`ghcr.io/larchanka-training/jsnotes-t2`)
- Deployment target — **Beget VPS** (Docker Compose over SSH; see section 6).
  The previous AWS stack is archived (tag `aws-deploy-archive-2026-07-05`)

### Code execution model
- **QuickJS** (WebAssembly) — a single engine intended for both the frontend
  and backend paths. The frontend path (Web Worker) is the MVP; the backend
  Execution Worker is the target/future path. See
  `docs/execution-architecture.md`.

---

## 4. Local run

Docker must be installed. Local domains require entries in `hosts`:

```
127.0.0.1 notebook.com
127.0.0.1 api.notebook.com
127.0.0.1 pgadmin.notebook.com
```

Start all services (frontend, api, postgres, pgadmin, proxy):

```bash
./start-services.sh           # or: docker compose up --build -d
```

Services (dev, `docker-compose.yaml`):

| Service | Port | Description |
|---|---|---|
| frontend | 3000 → 5173 | Vite dev server (`ui`) |
| api | 8000 | FastAPI with `--reload` (`api`) |
| postgres | 5432 | PostgreSQL 16 |
| pgadmin | 5050 | Web UI for the database |
| proxy | 80 / 443 | nginx reverse-proxy |

More on local domains, HTTPS and the proxy — the root `README.md` and
[`docs/Local-Proxy.md`](docs/Local-Proxy.md).

---

## 5. Tests and checks

| Where | Command | What it checks |
|---|---|---|
| `api/` | `pytest` | Backend unit/integration tests |
| `ui/` | `pnpm test` | Frontend Vitest tests |
| `ui/` | `pnpm lint` / `pnpm typecheck` | ESLint / TypeScript |
| `api/` | `python scripts/openapi.py bump --dry-run` | OpenAPI schema drift |

CI runs this automatically on a PR (section 6). For the UI/frontend — verify
changes in the browser, not only with tests.

---

## 6. CI/CD and deployment

### CI (GitHub Actions, `.github/workflows/`)

| Workflow | Purpose |
|---|---|
| `docker-compose-ci.yml` | Smoke test of the full compose stack (PR integration gate) |
| `build-images.yml` | Reusable (`workflow_call`): build api+ui+migrations → **GHCR** with the ephemeral per-run `GITHUB_TOKEN` (`packages: write`); tags chosen by event (`<prefix>-latest` on `main`, immutable `<prefix>-sha-<short>` always, semver on tags) |
| `ghcr-publish.yml` | Thin trigger on push `main`/tag → calls `build-images.yml` (prod images). Replaced `ecr-publish.yml` |
| `deploy-beget.yml` | Prod deploy — `workflow_run` after `GHCR Publish` on `main` (auto) + `workflow_dispatch` (manual/rollback with an explicit `image_tag`). SSH to the Beget VPS: `git reset --hard origin/main` (config sync) → `docker login ghcr.io` with the per-run token → `compose pull` → postgres healthcheck → Liquibase migrations as a one-off container (`contexts=production`, gated on exit 0) → `compose up -d` → smoke `GET /api/v1/health` == 200 |
| `autotests.yml` | Release-certification regression (issue #157): runs the standalone `autotests/` project via its containerized entrypoint (stack + migrations + pytest API + Playwright E2E + merged Allure). `workflow_dispatch` (smoke/regression/all) + nightly `schedule` + `pull_request` on `autotests/**`. Same command as the local pre-PR gate (§11) |

The retired AWS pipeline (`ecr-publish.yml`, `deploy-cloud.yml`,
`deploy-preview.yml`, `infra-*.yml`, `preview-sweep.yml`, `reset-db.yml`) is
preserved in [`archive/aws-workflows/`](archive/aws-workflows/README.md); the
full pre-migration state is at git tag `aws-deploy-archive-2026-07-05`.
Per-PR previews (preview-v2) were part of that AWS stack and are retired with
it — see [`docs/preview-v2.md`](docs/preview-v2.md) (archived).

Per-module lint/tests live in each submodule's own CI
(`api/.github/workflows/`, `ui/.github/workflows/`), not in the monorepo.

Images are published to a single GHCR repository, distinguished by tag prefix:
`ghcr.io/larchanka-training/jsnotes-t2:{api,ui,migrations}-<tag>`.

### Production run and deployment (Beget VPS)

Production is a single **Beget VPS** (2 vCPU / 4 GB, EU location) running
`docker-compose.prod.yaml` (project name `-p jsnotes`): postgres 16 + api +
frontend + nginx proxy, images pulled from GHCR. Environment — `.env.prod` on
the server (template `.env.prod.example`, `chmod 600`). Details —
[`docs/ci-cd.md`](docs/ci-cd.md).

**Live URL:** `https://jsnb.org` — UI at `/`, API at `/api/v1/*`.

- **Pipeline.** Merge to `main` → `ghcr-publish.yml` builds immutable
  `sha-<short>` images → `deploy-beget.yml` (`workflow_run`) deploys over SSH
  (pull → migrations → up → health gate).
- **TLS.** Public TLS terminates at **Cloudflare** (proxied, zone SSL = Full);
  the origin nginx listens on 443 with a **Cloudflare Origin Certificate**
  (`proxy/certs/`, server-local, git-ignored). nginx also sends the COOP/COEP
  headers required for cell execution (`SharedArrayBuffer`).
- **Secrets (GitHub Actions).** `BEGET_SSH_KEY` (dedicated deploy key),
  `BEGET_HOST`, `BEGET_USER`, `GH_PAT` (submodule checkout in builds).
  Runtime secrets (`JWT_SECRET`, `OTP_HASH_SECRET`, `RESEND_API_KEY`,
  Bedrock `AWS_ACCESS_KEY_ID`/`AWS_SECRET_ACCESS_KEY`) live only in the
  server's `.env.prod`.
- **LLM.** Amazon Bedrock (Nova Lite/Micro, `eu-north-1`) is still the LLM
  provider, reached with a narrow IAM key from `.env.prod` — the only remaining
  AWS dependency.
- **Rollback** — `deploy-beget.yml` (`workflow_dispatch`) with a previous
  **immutable** `sha-<short>` tag, not mutable `latest`.
- **Backups.** Beget node auto-backups (provider snapshots) + planned cron
  `pg_dump` (Ф11 of the migration plan).

---

## 7. Conventions for agents

- **Skills first.** `.agents/skills/` contains repo-specific workflow
  skills. For any non-trivial task start by loading
  [`notebook-planner`](.agents/skills/notebook-planner/SKILL.md) — it
  decomposes the work across submodules and docs, and tells you which
  other skill to load next (`notebook-ui`, `notebook-api`,
  `notebook-qa`, `notebook-quality-analysis`, `notebook-pr-review`,
  `merge-request-message`). After a task is completed, use
  [`create-session-artifacts`](.agents/skills/create-session-artifacts/SKILL.md)
  to generate the necessary review, learning, and memory records. Full index:
  [`.agents/skills/README.md`](.agents/skills/README.md).
- **Branches and PRs.** `main` is protected — changes go only through a
  feature branch and a PR. Do not push directly to `main`.
- **Submodules.** First commit + push in the submodule, then bump the pointer
  in the monorepo as a separate commit. Push order: submodule first, then the
  monorepo.
- **Git history.** Do not amend or force-push already published commits — only
  new commits on top.
- **Commits.** Create them only when the user explicitly asks.
- **Working in a submodule.** Inside `api/` and `ui/` follow their own
  `AGENTS.md` / `CLAUDE.md` and code style.
- **OpenAPI.** When the backend API changes, update `api/docs/openapi.json`
  (`scripts/openapi.py dump`). For **notebook**, the frontend generates
  from a vendored copy of that snapshot: in `ui`, run `pnpm api:vendor`
  (refreshes `ui/openapi/backend/openapi.json`) then `pnpm api:generate`.
  For **auth/llm**, hand-port the diff into the matching
  `ui/openapi/<domain>.openapi.yaml`, then `pnpm api:generate`. Full
  flow: `.agents/skills/notebook-api/references/openapi-sync.md`.

---

## 8. Documentation map `/docs`

| Document | About |
|---|---|
| [`System_Architecture.md`](docs/System_Architecture.md) | System architecture: frontend, backend, DB, data flows |
| [`execution-architecture.md`](docs/execution-architecture.md) | Cell code execution model: QuickJS hybrid, sandbox, errors, communication |
| [`ai-architecture.md`](docs/ai-architecture.md) | AI code-generation pipeline: execution strategy, Prompt Cell schema, AI Service API, Bedrock + WebLLM, validation, error handling |
| [`context-ai-workflow.md`](docs/context-ai-workflow.md) | AI generation **context** end-to-end: Context Builder, the `at-send`/`persisted` flag, incremental Mode B sync, backend persistence, summary strategies (`compact-oldest`/`llm`) |
| [`llm-rate-limiter-redis-roadmap.md`](docs/llm-rate-limiter-redis-roadmap.md) | Deferred roadmap for Redis/ElastiCache-backed shared LLM rate limiting: architecture, AWS options, costs, failure policy, and implementation phases |
| [`requirements.md`](docs/requirements.md) | Requirements, including LLM integration |
| [`project.md`](docs/project.md) | Project overview, functional requirements |
| [`backend-recommendations.md`](docs/backend-recommendations.md) | Backend stack recommendations |
| [`qa-plan.md`](docs/qa/qa-plan.md) | QA strategy, environments (AWS), test plan |
| [`autotest-tasks.md`](docs/qa/autotest-tasks.md) | Autotest roadmap (`AT-*`) + implementation status; see `autotests/` |
| [`qa-info.md`](docs/qa/qa-info.md) | Release-certification report (issue #157): regression results, known limitations, Go/No-Go |
| [`ci-cd.md`](docs/ci-cd.md) | DevOps notes, production Docker Compose |
| [`sprint-3-deliverables/README.md`](docs/sprint-3-deliverables/README.md) | **Sprint #3 deliverables — index:** source brief per workstream (Tech Lead, Engineers #1–#5, DevOps, QA), the file map, and contribution notes |
| [`sprint-3-deliverables/TL-production-readiness.md`](docs/sprint-3-deliverables/TL-production-readiness.md) | **Sprint #3 Tech Lead deliverable — production-readiness audit:** what breaks first, technical debt, release risks, and medium-term (3-month) engineering priorities |
| [`sprint-3-deliverables/E1-usage-analytics.md`](docs/sprint-3-deliverables/E1-usage-analytics.md) | **Sprint #3 Engineer #1 deliverable — usage analytics** _(not ready — template)_: planned event inventory (notebook creation, cell execution, AI requests, execution errors), event schema, and dashboard/implementation notes |
| [`sprint-3-deliverables/E2-cost-analysis.md`](docs/sprint-3-deliverables/E2-cost-analysis.md) | **Sprint #3 Engineer #2 deliverable — cost analysis:** monthly AWS/Bedrock/storage/traffic cost at 100/1,000/10,000 users across prod + preview, fixed-vs-variable split, assumptions, optimization recommendations |
| [`sprint-3-deliverables/E3-performance-report.md`](docs/sprint-3-deliverables/E3-performance-report.md) | **Sprint #3 Engineer #3 deliverable — performance report:** baseline for notebook open time, cell execution time, bundle size, and API latency (`larchanka-training/js-notebook#154`), with the cold-load/compression bottleneck and improvement proposals |
| [`sprint-3-deliverables/E4-security-review.md`](docs/sprint-3-deliverables/E4-security-review.md) | **Sprint #3 Engineer #4 deliverable — offensive security review:** XSS, JWT, API authorization, execution sandbox, prompt injection + an infra pass; findings anchored to `file:line`, deliberate trade-offs separated from genuine bugs |
| [`sprint-3-deliverables/E5-demo-day-outline.md`](docs/sprint-3-deliverables/E5-demo-day-outline.md) | **Sprint #3 Engineer #5 deliverable — demo day outline:** 15–20 min launch presentation structure (architecture, problems, solutions, mistakes, metrics, what worked, what to redesign) |
| [`sprint-3-deliverables/DevOps-runbook.md`](docs/sprint-3-deliverables/DevOps-runbook.md) | **Sprint #3 DevOps deliverable — Disaster recovery runbook:** scenarios A–G (DB loss, API down, region outage, secret leak, Bedrock budget, Resend OTP outage, sunset/handover) with ready AWS CLI commands, verification checklist, postmortem template, and 4 appendices (CLI shorthand, Logs Insights queries, kill switches, Terraform state DR) |
| [`sprint-3-deliverables/QA-release-report.md`](docs/sprint-3-deliverables/QA-release-report.md) | **Sprint #3 QA deliverable — release certification** _(not ready — template)_: regression summary, critical-bug list, known limitations, and the Go / No-Go release decision |
| [`aws-cloud-migration.md`](docs/aws-cloud-migration.md) | **(Archived)** The retired AWS cloud-native stack (ECS Fargate + RDS + S3/CloudFront): architecture, decisions, follow-ups. Kept as reference; snapshot at tag `aws-deploy-archive-2026-07-05` |
| [`preview-v2.md`](docs/preview-v2.md) | **(Archived)** Per-PR previews on the AWS stack: shared layer + per-PR UI (`/pr-N/`) and API (`/pr-N/api/v1`) slices, VPC endpoints (no NAT), routing, lifecycle, decisions A–D. Retired together with the AWS infrastructure |
| [`preview-dev-environments-v2.md`](docs/preview-dev-environments-v2.md) | Decision record (historical): preview-per-PR + prod evolution |
| [`bedrock-smoke-test.md`](docs/bedrock-smoke-test.md) | Runbook: live end-to-end check that the API can invoke Amazon Nova from a private subnet via the VPC endpoint and task IAM role (#113 Bedrock infra) |
| [`github-actions-pr-checks.md`](docs/github-actions-pr-checks.md) | PR checks |
| [`github-repository-settings.md`](docs/github-repository-settings.md) | Repository settings, environments, secrets |
| [`Local-Proxy.md`](docs/Local-Proxy.md) | Local nginx proxy and domains |

Submodule documentation lives in `api/docs/` and `ui/docs/` respectively.

---

## 9. Keeping documentation up to date

Documentation is part of the deliverable, not an optional appendix. If a
change affects logic described in the documents, the agent **must** update the
documentation synchronously, within the same scope of work:

- **Files in `docs/`.** When architecture, the execution model, the API,
  deployment, requirements, CI/CD, etc. change — update the corresponding
  documents in `docs/` (the map is section 8). A document must not contradict
  the code.
- **This file (`AGENTS.md`).** If the project's purpose, the repository
  structure, the tech stack, the run procedure, the CI/CD or deployment
  scheme, or the conventions change — update `AGENTS.md` so it stays a correct
  "entry" document for agents.
- **Scope.** Changing logic without updating the affected documentation counts
  as an unfinished task.
- **Consistency.** When code and a document disagree, the source of truth is
  the code; the document is brought in line, not the other way around.

---

## 10. Syncing `auth.md` between `api/` and `ui/`

The authorization document exists in two copies — one in each submodule:

- `api/docs/auth.md` — the backend side
- `ui/docs/auth.md` — the frontend side

These files describe **the same authorization contract** from two sides and
must stay consistent.

**Rule:** if `auth.md` changes in `api/` **or** in `ui/`, the change must be
made **in both** `auth.md` files at once — `api/docs/auth.md` and
`ui/docs/auth.md` — within a single task. Editing only one of them counts as
unfinished: the authorization contract must not diverge between frontend and
backend.

Since `api` and `ui` are separate submodule repositories, a synchronous edit
requires a commit in each of them (see the submodule discipline in sections
2 and 7).

---

## 11. Mandatory execution rules

Top-level rules that govern every task in this repository. Sections
1–10 above explain *how* the project is structured and *how* things
flow; this section is *what* must hold for every change.

Skills under `.agents/skills/` and references in `/docs` are
**supplemental** — they explain process and detail. They do not
override the rules below.

- **Don't expand task scope on your own.** Do only what the task
  artifact (issue, PR description, or explicit approval) asks for.
  Surrounding cleanup, drive-by refactors and "while we're here"
  additions are out of scope unless approved.
- **Don't add dependencies without approval.** New packages (npm,
  pip, GHCR images, GitHub Actions) require a stated reason and team
  alignment.
- **Don't change public contracts silently.** `api/docs/openapi.json`
  and the `auth.md` pair (`api/docs/auth.md` + `ui/docs/auth.md`)
  are public-facing contracts — every change to them is intentional,
  visible in the PR, and synchronised across consumers
  (see §7 OpenAPI rule and §10 `auth.md` rule).
- **Don't change architecture without updating docs.** If the change
  affects logic described in a document under `/docs/*.md`, update
  the document in the same PR (see §9).
- **Qualify every cross-repo issue/PR reference — in any text.** The
  project spans four GitHub repos: the central tracker
  `larchanka-training/js-notebook` (where **most issues live**, e.g.
  `.../js-notebook/issues/130`) plus this monorepo and the `ui`/`api`
  submodules — each with its **own** numbering. A bare `#NN` resolves
  to the **current** repo only, so across a repo boundary it silently
  mis-links or wrongly auto-closes a same-numbered issue/PR. Determine
  an issue's repo from its GitHub link/URL, never assume. In **every**
  text — commit messages, PR/MR titles and bodies, `gh` commands,
  docs, code comments — reference an issue/PR in another repo by its
  full `owner/repo#NN` form or full URL. Most issues live in `js-notebook`
  while code lands in mono/ui/api, so a fix PR is usually cross-repo
  and `Closes #NN` won't auto-close it — link with the full form and
  close the tracker issue manually. A bare `#NN` / `Closes #NN` is
  allowed **only** when the target is in the same repo as the text
  (see `.agents/rules/commit-message-rule.md`).
- **Add or update tests for behavior changes.** Static analysis
  doesn't prove behavior; tests do. CI lint passing is not a
  substitute for test coverage.
- **Run the containerized autotests before opening a PR.** Before
  forming a pull request, run the full regression with the stack
  brought up in containers:
  `autotests/scripts/run-containerized.sh regression` (host needs
  only Docker). Open the PR **only if it exits green** (API + E2E).
  See [`autotests/README.md`](autotests/README.md) and
  [`docs/qa/qa-info.md`](docs/qa/qa-info.md).
- **Treat untrusted input as untrusted.** User input, notebook
  content, LLM-generated code, and external API responses must be
  validated at the boundary they enter the system.
- **Never expose secrets.** `JWT_SECRET`, refresh tokens, OTP codes
  (in `prod`), LLM provider API keys, OAuth credentials must not
  appear in HTTP responses, structured logs, test fixtures, the
  OpenAPI snapshot, or commit messages.
- **Skills are supplemental.** Files under `.agents/skills/` and
  `.agents/rules/` give workflow guidance — they do not override
  this `AGENTS.md`, the documents under `/docs/`, or established
  codebase patterns.

---

## 12. Source of truth order

When sources conflict, there are **two separate questions** — keep
them apart:

**1. What is true (facts, contracts, behaviour) — lower number wins.**
The list runs concrete → abstract; the more concrete source is
authoritative. If two sources disagree about how the system *is*,
trust the lower-numbered one and bring the higher-numbered one in
line (§9).

1. Existing code and tests
2. Contracts: `api/docs/openapi.json`,
   `api/liquibase/changelog/**`, `.github/workflows/*.yml`
3. Submodule-specific docs: `ui/AGENTS.md`,
   `ui/docs/architecture/*`, `api/AGENTS.md`, `api/README.md`,
   `api/docs/auth.md`, `api/docs/ci-cd.md`
4. Architecture documents: `docs/System_Architecture.md`,
   `docs/execution-architecture.md`
5. This `AGENTS.md` and `docs/requirements.md`

So if `/docs/*.md` and code disagree, the **code** is the source of
truth and the document is brought in line (§9).

**2. What to do (scope of this change) — the approved task artifact
decides.** The currently approved task (issue, PR description,
explicit approval in a thread) controls *what* you are allowed to
change in this PR. It does **not** override the factual precedence
above — an approved task cannot make a stale doc "true", and it
cannot license a change that contradicts code/contracts without
first fixing them (§9, §11 "don't change public contracts
silently"). Scope authority ≠ factual authority.

Known drift cases this rule resolves:

| Doc says | Reality is | Source of truth |
|---|---|---|
| `docs/backend-recommendations.md` — Alembic | Liquibase | `api/README.md` + `api/liquibase/changelog/` |
| `docs/backend-recommendations.md` — email + password auth | Email OTP → JWT + refresh rotation | `api/docs/auth.md` |

When fixing a drift case, update the lower-precedence document in
the same PR (§9).

---

## 13. Canonical language

Multilingual at the doc layer, monolingual at the code layer.

- **`/docs/*.md` at the monorepo root** — English. PR #60 made this
  the canonical state. New documents added under `/docs/` are in
  English; mixed-language additions count as unfinished.
- **Submodule documentation** — language is the submodule team's
  decision and should stay internally consistent.
  `ui/docs/architecture/*` is in English; `api/docs/auth.md` is in
  Russian. Either is acceptable; a single doc mixing both is not.
- **Code, identifiers, code comments** — English. The codebase is
  multilingual at the doc layer but not at the code layer.
- **Commits and PR descriptions** — either language, author's
  choice, consistent within a single message (see
  `.agents/rules/commit-message-rule.md`).
- **Companion Russian summaries are not source of truth.** Per §12,
  when a Russian draft contradicts the English target document, the
  English target wins.
