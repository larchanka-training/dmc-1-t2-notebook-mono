# Preview environments (per-PR) — CI/CD layer

> **Status:** implemented on Terraform. Each PR gets its own EC2 + SG,
> provisioned via `terraform apply` (workspace `pr-<N>`), and removed via
> `terraform destroy` when the PR is closed. The preview URL is `http://<ip>/`,
> with no domain and no TLS (per the decision in the decision record).

## Idea

Each pull request gets its own Docker images (`api-pr-<N>` / `ui-pr-<N>` in
ECR) and its own ephemeral EC2 host. The environment lives while the PR is open.
The URL is published as a sticky comment in the PR itself.

## Workflow files

| File | Role |
| --- | --- |
| `.github/workflows/infra-bootstrap.yml` | **One-time** (`workflow_dispatch`): creates the S3 bucket `dmc-1-t2-notebook-terraform-state` for the Terraform state (versioning + SSE-AES256 + public-access-block) |
| `.github/workflows/build-images.yml` | **Reusable** (`workflow_call`): builds api+ui → ECR. The single source of build logic |
| `.github/workflows/ecr-publish.yml` | A thin trigger on push to `main` / tag → calls `build-images.yml` (prod images) |
| `.github/workflows/preview.yml` | On `pull_request` → calls `build-images.yml` (`pr-<N>`), then `terraform apply` workspace `pr-<N>` + SSH rollout + a sticky comment with the URL; on `closed` → `terraform destroy` + workspace deletion |
| `.github/workflows/docker-compose-ci.yml` | The integration smoke test of the stack on a PR (unchanged) |

The build is extracted into a reusable workflow so that prod and preview **do not
duplicate** the steps.

## Terraform infrastructure

The `terraform/` structure:

```
terraform/
├── bootstrap/        # bash script that creates the S3 bucket for tfstate
├── modules/
│   └── docker_host/  # reusable: EC2 + SG + user-data (Docker + SSH key)
├── prod/             # one state, imports the existing prod host
└── preview/          # workspace per PR (pr-<N>), its own EC2 + SG per PR
```

Backend — **S3 with native locking** (Terraform ≥ 1.10):

```hcl
backend "s3" {
  bucket       = "dmc-1-t2-notebook-terraform-state"
  key          = "preview/terraform.tfstate"
  region       = "eu-north-1"
  use_lockfile = true   # native S3 lock — DynamoDB not needed
  encrypt      = true
}
```

A DynamoDB table for locking is no longer used. The lock file is stored in the
bucket itself next to the state (a Terraform 1.10 feature).

> **The bucket name follows the course convention:** `dmc-1-t<team>-notebook-terraform-state`
> (ours is `dmc-1-t2-notebook-terraform-state`). The `deploy-user` IAM policy
> grants S3 access to exactly this name — an arbitrary name gives a `403`.

## Resource names

Each environment has two independent "names":

| What | Source | Can it be changed |
| --- | --- | --- |
| **SG group-name** | `var.name` (+ the `-sg` suffix) | ❌ immutable (ForceNew) — changing it recreates the SG |
| **EC2 Name tag** | `var.name_tag` (in the AWS console) | ✅ changes in-place |

They are **decoupled** on purpose: the SG name cannot be changed without
recreating the SG (and it cannot be deleted while attached to a live EC2). So
the meaningful name in the console is carried by the **Name tag**, not the
group-name.

The team's Name-tag convention:

| Environment | `var.name` (→ SG group-name) | `var.name_tag` (→ EC2 Name) |
| --- | --- | --- |
| prod | `jsnotes-t2-prod` → `jsnotes-t2-prod-sg` | `TARDIS-T2-prod` |
| preview | `jsnotes-preview-pr-<N>` → `…-sg` | `TARDIS-T2-preview-pr-<N>` |

For preview, `name_tag` is taken from `terraform.workspace` (= `pr-<N>`), so it
is substituted automatically. On prod, `name_tag` matches the already-existing
tag → `apply` causes no churn.

## Tags (chosen by `metadata-action` based on the event)

| Event | Tags in the ECR `jsnotes-t2` |
| --- | --- |
| push `main` | `api-/ui-latest` + `api-/ui-sha-<short>` |
| tag `v*.*.*` | `api-/ui-<semver>` |
| `pull_request` | `api-/ui-pr-<N>` (the repo is MUTABLE → overwritten on each push to the PR) |

Preview is built from the same Docker targets as prod (`api → runtime`,
`ui → production`), so preview mirrors prod rather than a dev build.

## Preview lifecycle

For each PR (`opened`/`synchronize`/`reopened`):

1. `build` — `api-pr-<N>` / `ui-pr-<N>` are built and pushed to ECR.
2. `deploy` — sequentially:
   - `terraform init` → `workspace select/new pr-<N>` → `apply`;
   - wait for cloud-init (Docker ready over SSH, up to 5 minutes);
   - `scp` `docker-compose.prod.yaml` + `proxy/nginx.prod.conf` + `.env.prod` → `~/app`;
   - on the host: `docker login` ECR (token from the runner via stdin) → `compose pull` → `up -d`;
   - smoke: `curl http://<ip>/api/v1/health`;
   - a sticky comment with the **working Preview URL** in the PR.

When the PR is closed (`closed`):

3. `teardown` — `terraform destroy` + `workspace delete pr-<N>` + update of the comment.

Concurrency:
- `preview-<N>-deploy`, `cancel-in-progress: true` — a new push to the PR
  cancels the previous preview build.
- `preview-<N>-teardown` — is **not** cancelled by build/deploy (important:
  otherwise an instance could be left without a destroy).

## .env for preview

Taken from the `PROD_ENV_FILE` secret (the same one as for prod). The workflow
overrides `IMAGE_TAG=pr-<N>` and `ECR_REGISTRY=...` on the fly. This gives the
preview environments the same OAUTH/POSTGRES/TTL values as prod — a deliberate
compromise for the duration of the course (there is no staging). If an isolated
set of `.env` for preview is needed later, we add a separate secret.

The file is placed at the **repo root** as `.env.prod` (not in `terraform/preview/`):
`docker-compose.prod.yaml` references `./.env.prod` via `env_file:` on the `api`
service, so the file must sit next to the compose file — otherwise
`docker compose config` fails with `env file ./.env.prod not found`.

## What you need to do once before the first PR

1. Run `Infra — Bootstrap Terraform state` (`workflow_dispatch`) to create the
   S3 bucket.
2. Run `Infra — Provision prod host (Terraform)` — it imports the existing prod
   EC2/SG into the state (or creates them if they do not exist).

After that, opening a PR automatically brings up a preview, and closing it tears
it down.

## Secrets / variables

| Name | Type | Purpose |
| --- | --- | --- |
| `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` | secret | `deploy-user` for AWS / ECR / Terraform |
| `SSH_PRIVATE_KEY` | secret | Private half of the key (the same as prod's). The public half is in `infra-prod.yml` / `preview.yml` (env `PREVIEW_SSH_PUBLIC_KEY`) |
| `PROD_ENV_FILE` | secret | Contents of `.env.prod` (DB, OAUTH, TTL); reused for preview |
| `GH_PAT` | secret | Reading submodules in the build phase |
| `GITHUB_TOKEN` | built-in | Sticky comments in the PR (`pull-requests: write`) |
| `AWS_REGION`, `VITE_API_BASE_URL` | vars | Region + the frontend base URL |

`deploy-user` permissions — all the required ones are granted (S3/DynamoDB are
optional; the code uses S3 + native locking; `ec2:TerminateInstances` /
`DeleteSecurityGroup` are needed for teardown).

## Gotchas (what we hit during the rollout)

| Symptom | Cause | Fix |
| --- | --- | --- |
| `403 Forbidden` on `HeadObject .../terraform.tfstate` | The bucket name does not follow the course convention — the `deploy-user` IAM policy grants S3 only on `dmc-1-t2-notebook-terraform-state` | Name the bucket per the convention |
| `terraform init`: `S3 bucket … does not exist` | On the first push, `infra-prod` starts in parallel with `infra-bootstrap` (a race) | Re-run `infra-prod` after bootstrap has created the bucket |
| The prod plan wants `destroy+create` of the SG (`# forces replacement`) | The `description` of `aws_security_group` is immutable; the code did not match the legacy SG | Keep `description` exactly as in the legacy SG (`"jsnotes-t2 prod: SSH + HTTP"`) |
| `Error acquiring the state lock` | A previous `apply` was cancelled halfway → a stale lock object was left | Delete `…/terraform.tfstate.tflock` from S3 (or `terraform force-unlock`) |
| `env file ./.env.prod not found` on `compose config` | `env_file: ./.env.prod` looks for the file next to the compose file | Write `.env.prod` to the repo root |

## Rolling back to the old setup (if something breaks)

The previous imperative version of `infra-prod.yml` is preserved in the git
history (before the commit that adds Terraform). Rollback — `git revert` +
remove the resources from the state before re-running. **Do not run `terraform
destroy` on prod** without an explicit decision — it would break the live site.
