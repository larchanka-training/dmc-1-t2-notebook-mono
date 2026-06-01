# Deploy Workflow

## Purpose

Deploys the prod environment from Docker images published to Amazon ECR onto a
long-lived EC2 host over SSH. It has three parts:

1. **Bootstrap state** — `infra-bootstrap.yml` creates the S3 bucket
   `dmc-1-t2-notebook-terraform-state` for the Terraform state (one-time).
2. **Bootstrap the host** — `infra-prod.yml` provisions the prod server via
   Terraform (or imports an existing one if it was created by the old
   imperative version). Uses the `terraform/modules/docker_host` module.
3. **Rollout** — on every update `deploy.yml` SSHes into the host and updates
   the containers (`docker compose pull && up -d`).

> **Terraform.** Backend — S3 (`dmc-1-t2-notebook-terraform-state`) with native locking
> (`use_lockfile = true`, Terraform ≥ 1.10). DynamoDB tables for locking are
> **not used** (a Terraform 1.10+ feature). Configs live in `terraform/prod/`.
> See [`preview.md`](preview.md) and
> [`preview-dev-environments-v2.md`](preview-dev-environments-v2.md).

## Deploy flow (on `main`)

```
push to main
   └─► ECR Publish (ecr-publish.yml) — builds api-/ui-latest into ECR
          └─► Deploy (deploy.yml, workflow_run after ECR Publish)
                 ├─ runner: aws ecr get-login-password  (ECR token)
                 ├─ ssh to host → docker login (token via stdin)
                 ├─ scp docker-compose.prod.yaml + proxy/ + .env.prod → ~/app
                 ├─ docker compose pull && up -d --remove-orphans
                 └─ smoke: curl http://<host>/api/v1/health
```

If the SSH secrets are not set, `deploy.yml` stays in **dry-run** (only tag and
compose validation, it does not reach the server). This is a safe default.

Workflow files:

```text
.github/workflows/infra-bootstrap.yml  # one-time: S3 bucket for Terraform state
.github/workflows/infra-prod.yml       # terraform apply of the prod host (+ import of an existing one)
.github/workflows/deploy.yml           # SSH rollout (+ dry-run fallback)
```

## Bootstrap state (one-time)

`infra-bootstrap.yml` (`workflow_dispatch`) creates the S3 bucket
`dmc-1-t2-notebook-terraform-state` with versioning, SSE-AES256 and block-public-access.
The script — `terraform/bootstrap/create-state-bucket.sh` — is idempotent.

Locking lives **in S3 itself** (`use_lockfile = true`). DynamoDB is not needed.

## Bootstrap the prod host (Terraform)

`infra-prod.yml` (`workflow_dispatch`) does the following:

1. `terraform init` — S3 backend (the state bucket must already exist).
2. **If there are no resources in the state yet**, it looks for the existing SG
   `jsnotes-t2-prod-sg` and a running EC2 in it → runs `terraform import`. This
   is the only way to take over a host that was previously created by the old
   imperative workflow without recreating it.
3. `terraform plan -detailed-exitcode` — exit code 1 fails the workflow (a guard
   against unintended destructive changes).
4. `terraform apply` — creates the host if it did not exist; otherwise a no-op.
5. Prints `public_ip` / `instance_id` into the Summary — these are the values
   for the `SSH_HOST` secret in `deploy.yml`.

The host is provisioned via the `terraform/modules/docker_host` module:
default VPC/subnet, a fresh Ubuntu 22.04 AMI (Canonical), an SG with ports
**22+80**, and user-data that installs Docker + the docker-compose-plugin and
adds the `ubuntu` SSH key. `lifecycle.ignore_changes = [ami, user_data]` —
a base AMI update or a refactor of the script does **not** trigger recreation of prod.

**Adopting the legacy SG (important).** The existing prod SG was created by the
old CLI with the description `"jsnotes-t2 prod: SSH + HTTP"`. On
`aws_security_group` the `description` field is immutable (ForceNew): any
mismatch → Terraform recreates the SG (and it cannot be deleted while it is
attached to a live EC2 → deadlock). So in `terraform/prod/main.tf` the
description is kept exactly as in the legacy SG. If you change it — reconcile
with the real SG.

**Name tag.** The EC2 is named via the `Name` tag (visible in the AWS console).
For prod — `TARDIS-T2-prod` (matches the already-existing tag → `apply` with no
churn), for preview — `TARDIS-T2-preview-pr-<N>`. The tag is set via
`var.name_tag`, which is **decoupled** from `var.name` (the latter is the SG
group-name, immutable). See [`preview.md`](preview.md), section "Resource names".

The key is created locally (`ssh-keygen`): the public half is baked into the
`PROD_SSH_PUBLIC_KEY` env inside `infra-prod.yml` (a public key is not a secret),
the private half lives in the `SSH_PRIVATE_KEY` secret (used by `deploy.yml`).

## How to run a rollout

**Auto:** after a merge to `main` and a successful `ECR Publish`, the deploy
runs on its own (`workflow_run`, tag `latest`, environment `production`). If the
`production` environment has required reviewers enabled, it waits for manual approval.

**Manually** (rollback or a specific tag): GitHub Actions → `Deploy` → Run workflow.

| Input | Allowed values | Example |
| --- | --- | --- |
| `image_tag` | a tag from ECR without the `api-`/`ui-` prefix | `latest`, `sha-8be47cc` |

## Secrets (repository)

A real rollout is enabled only when all four are set:

| Secret | Purpose |
| --- | --- |
| `SSH_HOST` | public IP of the prod host (from the `infra-prod` Summary) |
| `SSH_USER` | linux user (`ubuntu`) |
| `SSH_PRIVATE_KEY` | private half of the `jsnotes_prod` key |
| `PROD_ENV_FILE` | full contents of `.env.prod` (real DB/OAuth/TTL secrets) |

Also used (at the repository/organization level): `AWS_ACCESS_KEY_ID`,
`AWS_SECRET_ACCESS_KEY` (for `aws ecr get-login-password`), and the `AWS_REGION` var.

The ECR token is obtained **on the runner** and passed into `docker login` on
the host via stdin — the token is not written to the host's disk. An instance
IAM role is not used (`iam:CreateRole` is denied for `deploy-user`).

## What the deploy does (real mode)

1. `Decide deploy mode` → `real` if all SSH secrets + `PROD_ENV_FILE` are present.
2. Validates `image_tag` and `docker compose ... config`.
3. Builds `.env.prod` from `PROD_ENV_FILE` (overrides `IMAGE_TAG`/`ECR_REGISTRY`).
4. Prepares SSH (key + `ssh-keyscan`).
5. `scp` `docker-compose.prod.yaml`, `proxy/nginx.prod.conf`, `.env.prod` → `~/app`.
6. On the host: `docker login` ECR → `docker compose pull` → `up -d --remove-orphans` → `image prune -f`.
7. Smoke: `curl http://<host>/api/v1/health` (with retries).

Expected image names:

```text
867633231218.dkr.ecr.eu-north-1.amazonaws.com/jsnotes-t2:api-<image_tag>
867633231218.dkr.ecr.eu-north-1.amazonaws.com/jsnotes-t2:ui-<image_tag>
```

## Address

No domain/TLS yet — bare HTTP over the public IP:

```text
http://<SSH_HOST>/            # UI
http://<SSH_HOST>/api/v1/...  # API (through the same nginx)
```

The IP is stable until the instance is stopped/started. Elastic IP / domain /
TLS is a separate task.

## Rollback

The same `Deploy` (manual `workflow_dispatch`) with the previous **immutable**
tag, e.g. `sha-8be47cc` (not the mutable `latest`/`main`).

## GitHub Environments

The project has a single environment — `production` (no staging). You can attach
required reviewers to it so the auto-deploy after a merge waits for manual approval.

## deploy-user permissions (verified 2026-05-26)

| Action | Permission | Status |
| --- | --- | --- |
| Create an instance | `ec2:RunInstances` | ✅ |
| Create an SG | `ec2:CreateSecurityGroup` | ✅ |
| Open ports | `ec2:AuthorizeSecurityGroupIngress` | ✅ |
| Pull/push ECR | `ecr:*` | ✅ |
| Tag | `ec2:CreateTags` | ✅ |
| Delete/stop | `ec2:TerminateInstances` / `DeleteSecurityGroup` | ✅ (needed for preview teardown) |
| Terraform state (S3) | `s3:CreateBucket` / `s3:PutObject` | ✅ |
| Instance role | `iam:CreateRole` | ❌ (not used — ECR login over SSH) |
| DynamoDB lock | `dynamodb:CreateTable` | ❌ (not needed — `use_lockfile=true`) |

Prod is deployed onto a permanent host (we do not run `Terminate` for prod in CI
— that is a manual operation via the console or an explicit TF destroy). The ECR
login is done by the CI runner and the token is forwarded over SSH — an instance
IAM role is not required (`iam:CreateRole` is denied).
