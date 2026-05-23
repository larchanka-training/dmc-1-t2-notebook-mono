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
| `infra-prod.yml` | `workflow_dispatch` — one-time bootstrap of the prod EC2 host (SG + ports 22/80 + Docker via user-data); idempotent by SG membership (no tags — `ec2:CreateTags` denied) |
| `preview.yml` | On PR → calls `build-images.yml` (`pr-<N>` images) + sticky comment. Per-PR deploy/teardown **blocked**: needs `ec2:TerminateInstances`/`DeleteSecurityGroup` (requested from admin) |
| `deploy.yml` | `Deploy` — auto after `ECR Publish` on `main` (`workflow_run`) + manual `workflow_dispatch` for rollback. **Real SSH deploy** to the prod host when `SSH_*`/`PROD_ENV_FILE` secrets are set; dry-run otherwise |

Per-PR preview pipeline and its current scaffold are documented in
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

Current state and plan:

- **Prod — real deploy (SSH).** The host is a permanent EC2, bootstrapped once
  by `infra-prod.yml` (imperative AWS CLI, **not Terraform**). `deploy.yml` runs
  automatically after `ECR Publish` on `main` (`workflow_run`) and manually
  (`workflow_dispatch`) for rollback; it SSHes to the host, `docker login` to
  ECR (token piped from the runner), `docker compose pull && up -d`, then a smoke
  `curl /api/v1/health`. Without `SSH_*`/`PROD_ENV_FILE` secrets it falls back to
  dry-run. Full details — [`docs/deploy.md`](docs/deploy.md).
- **No Terraform (current constraint).** `deploy-user` lacks `s3:CreateBucket` /
  `dynamodb:CreateTable` (no remote state) and `ec2:CreateTags` /
  `TerminateInstances` / `DeleteSecurityGroup` / `iam:CreateRole`. It **can**
  `RunInstances` / `CreateSecurityGroup` / `AuthorizeSecurityGroupIngress` /
  `ecr:*`. Hence: prod is created imperatively, untagged (idempotency by SG
  membership), never auto-deleted, and pulls ECR via the runner-issued token.
- **Preview — blocked.** Per-PR build (`pr-<N>` images + comment) works, but the
  environment can't be torn down without `ec2:TerminateInstances` /
  `DeleteSecurityGroup` — requested from the course admin. See
  [`docs/preview.md`](docs/preview.md).
- **GitHub Environments.** Only `production` (enable required reviewers to gate
  the auto-deploy). Staging can be added later.
- **Secrets.** `SSH_HOST` / `SSH_USER` / `SSH_PRIVATE_KEY` / `PROD_ENV_FILE`
  (deploy), `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` (ECR). The deploy SSH
  public key is baked into `infra-prod.yml` user-data (public keys aren't secret).
- **Planned (upcoming sprints).** Domain, TLS, Elastic IP; preview once admin
  grants the two EC2 permissions; optional migration to Terraform if an S3 state
  bucket is provided.
- **Rollback** — the same `Deploy` workflow (manual) with the previous
  **immutable** tag (`sha-<short>`), not the mutable `latest`/`main`.

The full picture — [`docs/deploy.md`](docs/deploy.md).

---

## 7. Conventions for agents

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
  (`scripts/openapi.py dump`) — the frontend generates types from it.

---

## 8. Documentation map `/docs`

| Document | About |
|---|---|
| [`System_Architecture.md`](docs/System_Architecture.md) | System architecture: frontend, backend, DB, data flows |
| [`execution-architecture.md`](docs/execution-architecture.md) | Cell code execution model: QuickJS hybrid, sandbox, errors, communication |
| [`requirements.md`](docs/requirements.md) | Requirements, including LLM integration |
| [`project.md`](docs/project.md) | Project overview, functional requirements |
| [`backend-recommendations.md`](docs/backend-recommendations.md) | Backend stack recommendations |
| [`qa-plan.md`](docs/qa-plan.md) | QA strategy, environments (AWS), test plan |
| [`autotest-tasks.md`](docs/autotest-tasks.md) | Autotest tasks |
| [`ci-cd.md`](docs/ci-cd.md) | DevOps notes, production Docker Compose |
| [`deploy.md`](docs/deploy.md) | Deploy workflow (auto + manual) and deployment plan |
| [`preview-dev-environments-v2.md`](docs/preview-dev-environments-v2.md) | Decision record: preview-per-PR (dev) + prod. Terraform plan superseded (no S3 perms) → imperative; see 2026-05-24 update |
| [`preview.md`](docs/preview.md) | Preview per-PR CI/CD layer: workflows, tags, current scaffold |
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
