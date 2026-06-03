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
- **Offline mode.** Notebooks are stored locally in IndexedDB; syncing with
  the server is manual, triggered by a button.
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
├── terraform/                # AWS infrastructure (prod + preview-per-PR)
├── docker-compose.yaml       # local development (build from source)
├── docker-compose.prod.yaml  # production (prebuilt images from Amazon ECR)
├── .env.prod.example         # production environment template
├── start-services.sh         # quick local start
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
- **GitHub Actions** — CI/CD; images are published to **Amazon ECR**
- Target deployment infrastructure — **AWS** (see section 6)

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
| `build-images.yml` | Reusable (`workflow_call`): build api+ui → **Amazon ECR**; tags chosen by event |
| `ecr-publish.yml` | Thin trigger on push `main`/tag → calls `build-images.yml` (prod images) |
| `infra-bootstrap.yml` | `workflow_dispatch` — one-time creation of the S3 bucket `dmc-1-t2-notebook-terraform-state` (versioning, SSE, public-access-block) used as Terraform backend. Native S3 locking (`use_lockfile = true`, Terraform ≥ 1.10) — no DynamoDB |
| `infra-prod.yml` | `workflow_dispatch` — `terraform apply` of the prod host (`terraform/prod/`). Imports the existing EC2/SG into state on first run so the live prod is not recreated |
| `preview.yml` | On PR → calls `build-images.yml` (`pr-<N>` images), then `terraform apply` workspace `pr-<N>` (`terraform/preview/`) + SSH rollout + sticky comment with `http://<ip>/`. On `closed` — `terraform destroy` + `workspace delete` |
| `deploy.yml` | `Deploy` — auto after `ECR Publish` on `main` (`workflow_run`) + manual `workflow_dispatch` for rollback. **Real SSH deploy** to the prod host when `SSH_*`/`PROD_ENV_FILE` secrets are set; dry-run otherwise |

Per-PR preview pipeline (Terraform workspaces + SSH deploy) is documented in
[`docs/preview.md`](docs/preview.md); the architecture decision in
[`docs/preview-dev-environments-v2.md`](docs/preview-dev-environments-v2.md).

Per-module lint/tests live in each submodule's own CI
(`api/.github/workflows/`, `ui/.github/workflows/`), not in the monorepo.

Images are published to a single ECR repository, distinguished by tag prefix:
`867633231218.dkr.ecr.eu-north-1.amazonaws.com/jsnotes-t2:{api,ui}-<tag>`.

### Production run

`docker-compose.prod.yaml` brings up prebuilt images from Amazon ECR (no local
build). Environment — `.env.prod` (template `.env.prod.example`). Details —
[`docs/ci-cd.md`](docs/ci-cd.md).

### Deployment to AWS

The project's target infrastructure is **AWS**. Currently there is **only
`production`** (no staging yet); preview-per-PR environments are the "dev" side
(see [`docs/preview-dev-environments-v2.md`](docs/preview-dev-environments-v2.md)).

Current state:

- **Infrastructure as Code — Terraform.** All AWS-resources (prod EC2/SG and
  per-PR preview EC2/SG) live in `terraform/`. Backend: S3
  (`dmc-1-t2-notebook-terraform-state`) with native locking (`use_lockfile = true`,
  Terraform ≥ 1.10) — no DynamoDB. Structure:
  `terraform/{bootstrap, modules/docker_host, prod, preview}`.
- **Prod — Terraform + SSH.** `infra-prod.yml` runs `terraform apply` against
  `terraform/prod/`; on first run it `terraform import`s the existing EC2/SG
  so the live host is not recreated. `deploy.yml` then SSHes to the host
  (`docker login` ECR via runner-issued token → `compose pull && up -d` → smoke
  `curl /api/v1/health`). Runs automatically after `ECR Publish` on `main`
  (`workflow_run`) and manually for rollback. Without `SSH_*`/`PROD_ENV_FILE`
  secrets `deploy.yml` falls back to dry-run.
- **Preview-per-PR — Terraform workspaces.** `preview.yml` calls
  `terraform apply` in `terraform/preview/` with workspace `pr-<N>`, gets the
  EC2 public IP, SCPs compose + `.env.preview`, runs `docker compose pull && up`,
  posts a sticky PR comment with `http://<ip>/`. On `closed` PR — `terraform
  destroy` + `workspace delete`. URL is bare HTTP (no domain/TLS yet).
- **Permissions — `deploy-user`.** All required permissions granted (probed
  2026-05-26): `ec2:RunInstances/CreateSecurityGroup/AuthorizeSGIngress/CreateTags
  /TerminateInstances/DeleteSecurityGroup`, `ecr:*`, `s3:*` (state bucket).
  Not needed: `dynamodb:CreateTable` (native S3 locking), `iam:CreateRole`
  (ECR login via SSH from the runner, no instance profile).
- **GitHub Environments.** Only `production` (enable required reviewers to gate
  the auto-deploy). Staging can be added later.
- **Secrets.** `SSH_HOST` / `SSH_USER` / `SSH_PRIVATE_KEY` / `PROD_ENV_FILE`
  (deploy + preview reuses `PROD_ENV_FILE`), `AWS_ACCESS_KEY_ID` /
  `AWS_SECRET_ACCESS_KEY` (AWS / ECR / Terraform), `GH_PAT` (submodules).
  The SSH public key is baked into `infra-prod.yml` / `preview.yml` env
  (`PROD_SSH_PUBLIC_KEY` / `PREVIEW_SSH_PUBLIC_KEY`) — public keys aren't secret.
- **First-time setup.** Run `Infra — Bootstrap Terraform state` once
  (`workflow_dispatch`) to create the S3 bucket, then `Infra — Provision prod
  host (Terraform)` to import/create the prod EC2. After that PRs auto-deploy
  preview, merges to `main` auto-deploy prod.
- **Planned (upcoming sprints).** Domain + TLS for both prod and preview URLs;
  Elastic IP so prod IP survives stop/start.
- **Rollback** — the same `Deploy` workflow (manual) with the previous
  **immutable** tag (`sha-<short>`), not the mutable `latest`/`main`.

The full picture — [`docs/deploy.md`](docs/deploy.md) and
[`docs/preview.md`](docs/preview.md).

---

## 7. Conventions for agents

- **Skills first.** `.agents/skills/` contains repo-specific workflow
  skills. For any non-trivial task start by loading
  [`notebook-planner`](.agents/skills/notebook-planner/SKILL.md) — it
  decomposes the work across submodules and docs, and tells you which
  other skill to load next (`notebook-ui`, `notebook-api`,
  `notebook-qa`, `notebook-quality-analysis`, `notebook-pr-review`,
  `merge-request-message`). Full index:
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
  (`scripts/openapi.py dump`). The frontend does **not** read that
  snapshot directly — hand-port the diff into the matching
  `ui/openapi/<domain>.openapi.yaml`, then `pnpm api:generate`. Full
  flow: `.agents/skills/notebook-api/references/openapi-sync.md`.

---

## 8. Documentation map `/docs`

| Document | About |
|---|---|
| [`System_Architecture.md`](docs/System_Architecture.md) | System architecture: frontend, backend, DB, data flows |
| [`execution-architecture.md`](docs/execution-architecture.md) | Cell code execution model: QuickJS hybrid, sandbox, errors, communication |
| [`ai-architecture.md`](docs/ai-architecture.md) | AI code-generation pipeline: execution strategy, Prompt Cell schema, AI Service API, Bedrock + WebLLM, validation, error handling |
| [`requirements.md`](docs/requirements.md) | Requirements, including LLM integration |
| [`project.md`](docs/project.md) | Project overview, functional requirements |
| [`backend-recommendations.md`](docs/backend-recommendations.md) | Backend stack recommendations |
| [`qa-plan.md`](docs/qa-plan.md) | QA strategy, environments (AWS), test plan |
| [`autotest-tasks.md`](docs/autotest-tasks.md) | Autotest tasks |
| [`ci-cd.md`](docs/ci-cd.md) | DevOps notes, production Docker Compose |
| [`deploy.md`](docs/deploy.md) | Deploy workflow (auto + manual) and deployment plan |
| [`preview-dev-environments-v2.md`](docs/preview-dev-environments-v2.md) | Decision record: preview-per-PR (dev) + prod, now on Terraform with S3 native locking; see 2026-05-26 update |
| [`preview.md`](docs/preview.md) | Preview per-PR CI/CD layer: Terraform workspaces, lifecycle, sticky comment with URL |
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
- **Add or update tests for behavior changes.** Static analysis
  doesn't prove behavior; tests do. CI lint passing is not a
  substitute for test coverage.
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
