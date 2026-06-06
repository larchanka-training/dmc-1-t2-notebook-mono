# Preview + Dev Environments v2 — decision and plan

> **⚠️ Historical decision record — superseded. NOT a current runbook.**
> This documents the *original* EC2 + docker-compose approach (Terraform
> `terraform/{prod,preview,modules/docker_host}`, SSH rollout, workspace-per-PR,
> bare-IP `http://<ip>/` preview URLs). **That whole stack has been fully
> decommissioned and removed.** This file is kept only as a timeline of how the
> decision evolved. For how things actually work now, see
> [`aws-cloud-migration.md`](aws-cloud-migration.md) (cloud prod: ECS/RDS/S3/CloudFront)
> and [`preview-v2.md`](preview-v2.md) (per-PR previews on CloudFront). Everything
> below describes the previous, now-removed implementation — read it as history,
> not as instructions.
>
> _Original status (2026-05-23): decision record + partially implemented._

> **🔄 UPDATE (2026-05-24) — results of the `deploy-user` permissions probe.**
> A real permissions check changed the plan (details — in `deploy.md`):
> - **Terraform was dropped** for prod and preview: `s3:CreateBucket` /
>   `dynamodb:CreateTable` are denied → there is nowhere to store the remote state.
> - **Prod is done and working** — imperatively (CLI, `infra-prod.yml` creates the EC2)
>   + a real SSH rollout (`deploy.yml`). `deploy-user` can
>   `RunInstances`/`CreateSecurityGroup`/`AuthorizeSecurityGroupIngress`/`ecr:*`.
> - **Preview is blocked**: `ec2:TerminateInstances` / `DeleteSecurityGroup`
>   (nothing to tear down the PR environment with) and `ec2:CreateTags` are denied.
>   Two delete permissions were requested from the admin. The approach will be
>   **imperative** (a per-PR security group instead of tags/Terraform),
>   independent of S3.

> **🔄 UPDATE (2026-05-26) — all permissions granted, Terraform adopted.**
> The admin granted the missing permissions (`s3:CreateBucket`, `ec2:TerminateInstances`,
> `ec2:DeleteSecurityGroup`, `ec2:CreateTags`). The resulting decisions:
> - **Terraform is back** — for both prod and preview. Without DynamoDB:
>   the S3 backend uses **native locking** (`use_lockfile = true`,
>   Terraform ≥ 1.10). The state bucket is created by a one-time workflow
>   `Infra — Bootstrap Terraform state`.
> - **Prod** — `terraform/prod/`. The existing EC2/SG is **imported** on the
>   first run (`terraform import`), not recreated.
> - **Preview** — `terraform/preview/`, **workspace per PR** (`pr-<N>`). Each
>   PR gets its own EC2 + SG + Preview URL (`http://<ip>/`, no TLS).
>   Teardown via `terraform destroy` + `workspace delete` on `pull_request: closed`.
> - **Per-PR SG name** — `jsnotes-preview-pr-<N>-sg`, derived from
>   `terraform.workspace` (not from manual tags).
> - **Domain/TLS** — not yet: the preview URL = `http://<public IP>/`. This is a
>   deliberate simplification for the duration of the course; domain/TLS is a
>   separate task.
> - **`.env` for preview** — reused from the `PROD_ENV_FILE` secret (there is no
>   staging in the course; a separate set can be added later).
>
> The sections below ("Tool — Terraform", "workspaces", open questions) are the
> original design decision; they described the (now-removed) EC2 implementation at
> the time and are retained as history only.

## Context / task

Extend the infrastructure into a "live" product (`DEV + PROD`). Required:

- preview deployments for each branch / pull request;
- automatic deploy on merge into `main`;
- build caching optimization.

Result: working **preview URLs for each PR** + an updated CI/CD pipeline.

Related handoff: `docs/github-repository-settings.md` → the section "Handoff for
the Next DevOps: Preview + Dev Environments v2".

## Key decisions

### 1. Branching model — GitHub Flow

`feature → PR → main` directly. There is **no** separate long-lived `dev`
branch. The role of "a place to verify before prod" is played by each PR's
preview environment, not by a shared intermediate branch.

### 2. Two environment types (not three)

| Type | Also known as | When it comes up | How long it lives | Code source |
| --- | --- | --- | --- | --- |
| **dev / preview / PR** | "DEV" from the task | PR opened/updated | while the PR is open | the PR branch |
| **prod** | "PROD" from the task | merge to `main` | permanently | `main` |

`dev` = `preview` = `pr` — these are one and the same environment under different
names. We deploy to two environment types, not three.

### 3. Tool — Terraform (Infrastructure as Code)

A `plan → apply` cycle for prod and `plan → apply → destroy` for preview.
We base it on examples from
[futurice/terraform-examples](https://github.com/futurice/terraform-examples):

| Example | What we take |
| --- | --- |
| `aws_ec2_ebs_docker_host` | the EC2 host skeleton + an EBS volume (for PostgreSQL data) |
| `docker_compose_host` | the pattern of delivering and running `docker-compose` on the host |
| `aws_reverse_proxy` | optionally — nice `pr-<N>.preview.<domain>` instead of a bare IP |

### 4. Per-PR isolation — Terraform workspaces

Each PR = workspace `pr-<N>` with its own state, so the environments do not
overwrite each other. On `pull_request: opened/synchronize` → `apply` brings up
this PR's ephemeral EC2 docker host (its own PostgreSQL container + EBS) and runs
`docker compose` on it with the `api-pr-<N>` / `ui-pr-<N>` images from ECR. On
`pull_request: closed` → `destroy`.

Prod — a separate long-lived workspace `prod`.

### 5. Reusing what exists

- `ecr-publish.yml` — build + push to ECR (`jsnotes-t2`, tags `api-`/`ui-`).
  **Build caching is already done** (`type=gha, mode=max`, separate scopes for
  api/ui) — requirement #3 is essentially closed.
- `docker-compose.prod.yaml` — a stack of prebuilt ECR images.

## Target architecture

```
GitHub PR ──► CI (GitHub Actions)
                 │ build api+ui ──► push to ECR (jsnotes-t2)        ← already exists
                 │
                 ├─ PR opened:   terraform workspace pr-<N> → plan → apply
                 │                 └─► EC2 docker host (its own) → docker compose up
                 │                       └─► Preview URL → comment in the PR (+ EMAIL_KEY?)
                 │
                 └─ PR closed:   terraform destroy → instance removed

merge to main ──► build/push (exists) → terraform apply (prod) → compose pull/up
```

## What changes in the pipeline

| Workflow | Action |
| --- | --- |
| `ecr-publish.yml` | unchanged (build + cache are already done) |
| `docker-compose-ci.yml` | stays as the PR smoke test (this is not preview) |
| `deploy.yml` | rework: manual dry-run → auto-deploy prod on `push: main` |
| `preview.yml` | **new**: apply on PR / destroy on close + a comment with the URL |
| `terraform/` | **new**: backend (remote state) + an environment module |

## Secrets and variables

Already set up (see `docs/github-repository-settings.md` — that section needs an
update, see the discrepancies found below):

- Secrets: `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `EMAIL_KEY`, `GH_PAT`.
- Variables: `AWS_REGION=eu-north-1`, `AWS_REPO_NAME=jsnotes` (generic; in the
  pipeline the repository name is **hardcoded** as `jsnotes-t2`).

Additionally needed: a backend for the remote state (S3 + DynamoDB lock) and,
possibly, secrets for the domain/TLS.

## Implementation plan (order)

0. Close the open questions (below).
1. The `terraform/` skeleton: backend (remote state) + an environment module
   (EC2 docker host + SG + EBS + Elastic IP).
2. **Manually** `terraform apply` one environment → a working app at a public
   address. The main checkpoint: the path Terraform → EC2 → ECR → live URL.
3. `preview.yml`: wrap step 2 in Actions (workspace per PR, apply/destroy, a
   comment with the preview URL).
4. `deploy.yml`: auto-deploy prod on merge to `main`.
5. Build caching — already done, note it in the report.

## Implementation status (updated as work proceeds)

**Implemented (2026-05-23):**

- `build-images.yml` — a reusable workflow that builds api+ui → ECR; tags by
  event (`latest`/`sha`/`semver`/`pr-<N>`).
- `ecr-publish.yml` — switched to a thin call of `build-images.yml` (prod).
- `preview.yml` — on a PR it builds `pr-<N>` images, validates the prod compose
  with that tag, posts a sticky comment in the PR; on PR close — a teardown step.
- `deploy.yml` — renamed to `Deploy`; added an **auto-trigger**
  `workflow_run` after `ECR Publish` on `main` (+ kept the manual mode for
  rollback). This closes "auto-deploy on merge" at the trigger level.
- Build caching — was done earlier, moved into the reusable workflow.

Workflow-layer details — [`preview.md`](preview.md).

**Update (2026-05-24):**

- ✅ **Prod is deployed for real** — `infra-prod.yml` (bootstrap EC2) + `deploy.yml`
  (SSH → ECR → `compose pull && up` → smoke). Imperatively, without Terraform.
- ⛔ **Preview is blocked** by permissions: no `ec2:TerminateInstances` /
  `DeleteSecurityGroup` (nothing to tear down with). Requested from the admin.
- ❌ **The Terraform infrastructure** is not being done — no permissions for S3/DynamoDB for the state.

**Update (2026-05-26) — Terraform + preview enabled:**

- ✅ **Terraform adopted** — `terraform/{bootstrap,modules/docker_host,prod,preview}/`.
  Backend — S3 with `use_lockfile = true` (Terraform ≥ 1.10), without DynamoDB.
- ✅ **Prod** is managed by Terraform (`terraform/prod/`); the existing EC2/SG is
  imported (`terraform import` in `infra-prod.yml`), not recreated.
- ✅ **Preview-per-PR** works: workspace `pr-<N>` → its own EC2 + SG → SSH rollout
  of compose → a sticky comment with `http://<ip>/`. On a `closed` PR — `destroy`.
- ⏳ **Domain/TLS** — not yet; the preview URL has no TLS, over a bare IP.

## Open questions (to clarify with the course)

1. **Remote state.** ⛔ ANSWERED by the probe (2026-05-24): `deploy-user` CANNOT
   `s3:CreateBucket` / `dynamodb:CreateTable` → it cannot create the state
   backend on its own → **Terraform deferred**. Open to the admin: provide a
   ready S3 bucket (+DynamoDB) OR the permissions to create them — then we can
   go back to Terraform.
2. **Per-PR hosting.** A dedicated EC2 per PR (Terraform workspaces, a clean
   `destroy`) or a shared host + per-PR `docker compose -p`? The default
   decision — a dedicated EC2.
3. **Domain/DNS.** Is there a zone for `*.preview.<domain>` or is the preview URL
   = the public IP / the instance's DNS name?
4. **`EMAIL_KEY`.** For sending preview links / deploy notifications? Which
   provider (SES / SendGrid / Resend)?
5. **Instance size and auto-removal.** Type (`t3.micro/small`?), tear down the
   preview when the PR is closed (and possibly on an inactivity timeout)?
6. **Environment model — DECIDED (2026-05-23):** the project has only `production`
   (+ preview-per-PR). There is **no** staging yet. `deploy.yml` is simplified to
   prod-only; the auto-deploy targets `production`. Staging can be added later as
   a separate task (bring back the `environment` input + set up a GitHub Environment).
   ⚠️ `docs/qa-plan.md` (Local/CI/Staging/Production) and
   `docs/github-repository-settings.md` (Environments `staging`/`production`)
   still describe staging — fix them together with the rest of the pending doc edits.

## Documentation audit: discrepancies found (doc ≠ code)

> Checked against the real workflows on 2026-05-23. **The edits to the docs
> themselves have not been made yet** — they await sign-off on each item. The
> verified discrepancies are recorded here so they can be fixed deliberately and
> consistently.

**The main thing:** the repository contains **three inconsistent environment
models** — `staging`/`production` (`deploy.yml`, `deploy.md`, `AGENTS.md §6`,
`github-repository-settings.md`), Local/CI/Staging/Production (`qa-plan.md §5`,
lines 179–186) and `dev`=preview-per-PR + `prod` (this task). Reconciling them is
open question #6 above.

| # | File | Discrepancy | Confirmation in the code |
| --- | --- | --- | --- |
| 1 | `docs/ci-cd.md` (line 10) | "Frontend and Backend are deployed **separately**": they are built/published as 2 images — yes, but they are **deployed together** as one stack `docker-compose.prod.yaml`. (The part about per-module CI and docs in the submodules is **correct**.) | `docker-compose.prod.yaml`; below in `ci-cd.md` itself the single production compose is described |
| 2 | `docs/github-actions-pr-checks.md` (lines 44–59) | "Docker Build" is placed inside **API CI / UI CI (= the submodules' CI)**, where there is no Docker build. In reality the images are built in the monorepo: `docker compose build` on a PR and `build-push-action` on main/tag. The real jobs `CI complete` and UI `Unit tests` (coverage) are omitted | `api/.github/workflows/pull-request.yml` (lint/test/ci-complete), `ui/.github/workflows/pull-request.yml` (lint/test/build/ci-complete); `docker-compose-ci.yml:49`; `ecr-publish.yml:95` |
| 3 | `docs/github-actions-pr-checks.md` (lines 26–30) | submodule checkout is shown as `with: token` + `submodules: recursive`, whereas the workflows use the **manual** way `git config url.insteadOf` + `git submodule update` | `docker-compose-ci.yml:33-36`, `ecr-publish.yml:59-62` |
| 4 | `docs/github-repository-settings.md` (lines 193–221) | The Secrets/Variables tables are incomplete: missing the currently-**used** `AWS_ACCESS_KEY_ID`/`AWS_SECRET_ACCESS_KEY` (secrets), `AWS_REGION`/`AWS_REPO_NAME` (vars), as well as `SSH_*` and `EMAIL_KEY`. The currently-unused `DATABASE_URL`/`OAUTH_*`/`*_TTL` are listed | `grep secrets./vars.` over `.github/workflows/` |
| 5 | `docs/deploy.md` (lines 86–98) | `AWS_ACCESS_KEY_ID`/`AWS_SECRET_ACCESS_KEY` are marked as "future" secrets, but they are already used. "Future" — only `SSH_*` | `ecr-publish.yml:72-73` |

Additionally:

- `EMAIL_KEY` — the secret is set up (from a course screenshot), but it is **not
  used** in the code — a placeholder for v2 notifications.
- The ECR name `jsnotes-t2` and the tag scheme `api-`/`ui-` are **consistent**
  across all files. ✅

**Edit status: APPLIED (2026-05-23).** All discrepancies are fixed in the docs:

- `ci-cd.md` — "deployed separately" → "built separately, deployed together";
  generic `staging` → `production`;
- `github-actions-pr-checks.md` — removed the phantom `Docker Build`, added the
  real jobs (`Unit tests`/`CI complete`), fixed the submodule checkout method;
- `github-repository-settings.md` — Secrets/Variables extended (`AWS_*`,
  `EMAIL_KEY`, `SSH_*`, `AWS_REGION`/`AWS_REPO_NAME`), Environments → prod-only,
  `Manual Deploy` → `Deploy`, the required-checks table updated;
- `deploy.md`, `AGENTS.md` — `Manual Deploy` → `Deploy`, auto+manual, prod-only;
- `qa-plan.md` — a note that staging is not deployed yet (the target model).

The only thing still open: the exact names of the nested checks (ECR Publish/Preview)
after the reusable refactor — verify in the GitHub UI before making them required.
