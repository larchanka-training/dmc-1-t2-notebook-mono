# AWS cloud-native migration

Migration of T2 from the current single EC2 + docker-compose prod to a
cloud-native stack on AWS (ECS Fargate + RDS + S3/CloudFront). Tracked as a
single umbrella task: `larchanka-training/js-notebook`#110. Work happens on the
`feat/cloud-migration` branch and is merged to `main` only after the stack is
set up and verified.

> Reference: the sibling team T1 (`dmc-1-t1-notebook-mono`, `infra/`) already
> built a comparable stack; we copy/adapt their network/ALB/ECS patterns and
> improve on them (immutable image tags, native S3 locking, a real
> destructive-change guard, TLS, frontend on CloudFront instead of ECS).

## Target architecture

```
Route53 → CloudFront ─┬─ /*        → S3 (React static)
        (ACM TLS)     └─ /api/v1/* → ALB → ECS Fargate (api) → RDS
                                            ↑ Secrets Manager (DATABASE_URL)
                                            ↑ CloudWatch Logs
```

## Decisions

- **ECS Fargate** (not ECS-on-EC2): covered by the granted `deploy-user`
  permissions, no node/ASG management.
- **Frontend on S3 + CloudFront** (prod UI served from the CDN, not from an ECS
  service — simpler/cheaper than T1).
- **Registry:** Amazon ECR with **immutable `sha-<short>` tags** (rollback +
  Terraform sees image changes), not mutable `:latest`.
- **State backend:** S3 with **native locking** (`use_lockfile = true`,
  Terraform ≥ 1.10), no DynamoDB. Separate state key `cloud/terraform.tfstate`
  so the cloud stack never touches the live EC2 prod / preview state.
- **Preview (variant A):** per-PR **static frontend** in S3 + CloudFront
  (`/pr-<N>/`), with the API pointing at a single shared non-prod backend — no
  per-PR EC2. (Implemented in a later phase.)
- **Deferred / not done:** SES (email OTP won't work in the cloud env until
  added), observability (CloudWatch alarms / SNS), auto-scaling, WAF,
  API Gateway, bastion (use ECS Exec instead).

## Terraform layout

```
terraform/
├── cloud/                # root stack for the cloud-native env
│   ├── backend.tf        # S3 state, key=cloud/terraform.tfstate, native locking
│   ├── providers.tf      # aws (eu-north-1) + alias us_east_1 (for CloudFront ACM)
│   ├── versions.tf       # Terraform >= 1.10, aws ~> 5.70
│   ├── variables.tf      # project=jsnotes-t2, region, image_tag, api_desired_count
│   ├── main.tf           # composes the modules (network, backend, frontend, data)
│   └── outputs.tf
└── modules/
    ├── network/          # Phase 0 — VPC, subnets, NAT, route tables, SG chain
    ├── backend/          # Phase 1 — IAM, Secrets, ECS Fargate, ALB, CloudWatch
    ├── frontend/         # Phase 2 — S3 (private + OAC) + CloudFront
    └── data/             # Phase 3 — RDS PostgreSQL + DATABASE_URL secret value
```

The legacy EC2 prod (`terraform/prod`) and preview (`terraform/preview`) stacks
are left untouched; the cloud stack is additive and isolated.

## Phases

| Phase | Scope | Status |
| --- | --- | --- |
| **0. Network** | VPC, public/private subnets (2 AZ), IGW, NAT, route tables, SG chain | **applied 2026-06-03** (VPC-per-Region quota raised in `eu-north-1`) |
| **1. Backend** | IAM roles, Secrets Manager, ECS Fargate cluster/task/service, ALB, CloudWatch logs | **applied** (`terraform/modules/backend`). `api_desired_count=1`. Tasks retry until the DB has a schema. **Liquibase migration runner implemented** — a dedicated `jsnotes-t2-migrations` task definition + `jsnotes-t2-db-migration` secret; `deploy-cloud.yml` runs it as a one-off `run-task` before the API rolls out |
| **2. Frontend** | S3 (private + OAC) + CloudFront (`/*` → S3 SPA, `/api/v1/*` → ALB) | **applied** (`terraform/modules/frontend`). CloudFront `d3mdkzwy5yknm5.cloudfront.net` (dist `E29EW3R1X0PB5W`). Managed cache policies, CloudFront Function for SPA, default cloudfront.net cert (custom domain in TLS phase) |
| **3. Data** | RDS PostgreSQL (encrypted, backups, deletion protection) + data migration | **applied** (`terraform/modules/data`): Postgres 16, db.t3.micro, encrypted, 7-day backups, deletion protection, final snapshot. Master username `jsnotes` (**`admin` is a PG reserved word — RDS rejects it; fixed in `7dfb256`**). DATABASE_URL secret value written. Schema migration runs at deploy time via the Liquibase migration task (see CI row); the migration creds are in the `jsnotes-t2-db-migration` secret |
| TLS | Route 53 + ACM (HTTPS) — needs Route53/ACM permissions | not started |
| Preview | per-PR preview that beats T1 + current (per-PR frontend + Fargate backend + `pr_<N>` DB) | **design done** — see [`preview-v2.md`](preview-v2.md); build after apply |
| **CI** | ECS deploy (immutable tags) + frontend S3/CloudFront | **applied & ready** (`deploy-cloud.yml`, `workflow_dispatch`): registers a new task-def revision, `update-service`, waits stable, smoke; frontend = extract static from the ui image → `s3 sync` → CloudFront invalidation. ECS service uses `ignore_changes=[task_definition]` so Terraform doesn't fight the pipeline. **Liquibase migrations run as a one-off `run-task`** (registers a `migrations-<tag>` revision, runs in the API service's network config, gated on exit code 0) before `update-service`. The `migrations-<tag>` image is built by `build-images.yml` alongside api/ui. Add a `workflow_run`-after-ECR-Publish trigger at cutover |

## Phase 0 — network (done)

`terraform/modules/network` creates (~19 resources):

- **VPC** `10.0.0.0/16` (`enable_dns_hostnames/support` for RDS/service DNS).
- **Subnets**, two tiers across the first two AZs (`count = 2`):
  - public `10.0.1.0/24`, `10.0.2.0/24` — ALB + NAT (`map_public_ip_on_launch`).
  - private `10.0.11.0/24`, `10.0.12.0/24` — ECS tasks and RDS (no public IP).
- **Internet gateway** + **single NAT gateway** (with an EIP) in a public subnet
  — private-subnet egress for image pulls / external APIs. A single NAT is a
  deliberate cost/availability trade-off.
- **Route tables:** public `0.0.0.0/0 → IGW`, private `0.0.0.0/0 → NAT`, with
  associations to both AZs.
- **Security-group chain** (least-privilege, no SSH anywhere):
  - `alb` — 80/443 from the internet;
  - `ecs` — API port (8000) **only from the ALB SG**;
  - `rds` — 5432 **only from the ECS SG**.

Outputs (`vpc_id`, `public/private_subnet_ids`, `alb/ecs/rds_security_group_id`)
feed the later phases.

### CI workflow

`.github/workflows/infra-cloud.yml` runs Terraform for the cloud stack:

- **pull_request** (paths `terraform/cloud/**`, `terraform/modules/network/**`)
  → `init` + `validate` + `plan` (read-only).
- **workflow_dispatch** → `plan` or `apply` (+ `allow_destroy`).
- **push to `feat/cloud-migration`** → apply from the branch. **TEMPORARY** — to
  be removed before merging to `main` (`workflow_dispatch` needs the workflow on
  the protected `main` branch, hence the branch trigger during development).
- **Destructive-change guard:** parses `terraform show -json` and fails the run
  if the plan would `delete`/replace any resource, unless `allow_destroy=true`.
  This is a real guard, unlike a bare `-detailed-exitcode`.

### Apply & verify

```bash
terraform -chdir=terraform/cloud init
terraform -chdir=terraform/cloud plan          # expect ~19 to add, 0 change, 0 destroy
terraform -chdir=terraform/cloud apply
terraform -chdir=terraform/cloud output        # vpc_id, subnet ids, sg ids
```

After apply, verify in AWS (region `eu-north-1`): VPC `jsnotes-t2-vpc`, 4 subnets
in 2 AZs, NAT `available`, private route table → NAT, and the SG chain
(`ecs` ingress from `alb`, `rds` ingress from `ecs`).

### Applied (2026-06-03)

The full cloud stack (network + backend + frontend + data) is `terraform apply`-ed
in `eu-north-1`. Two blockers were cleared on the way:

1. **`VpcLimitExceeded`** — the shared course account hit the default **5 VPCs per
   region** limit in `eu-north-1`. Unblocked by raising the **"VPCs per Region"
   quota (`L-F678F1CE`)** (Service Quotas; soft limit, needed AWS approval).
2. **RDS `MasterUsername admin ... is a reserved word`** — `db_username` defaulted
   to `admin`, which PostgreSQL on RDS rejects. Fixed by defaulting it to `jsnotes`
   (commit `7dfb256`); the same variable feeds both the instance and the
   `DATABASE_URL` secret, so they stay consistent.

Live outputs:

| output | value |
| --- | --- |
| `cloudfront_domain_name` | `d3mdkzwy5yknm5.cloudfront.net` |
| `alb_dns_name` | `jsnotes-t2-alb-1550399577.eu-north-1.elb.amazonaws.com` |
| `db_endpoint` | `jsnotes-t2-db.cxcy464kspzj.eu-north-1.rds.amazonaws.com:5432` |
| `ecs_cluster_name` | `jsnotes-t2` |
| `frontend_bucket` | `jsnotes-t2-frontend` |
| CloudFront distribution id | `E29EW3R1X0PB5W` |

**Infra up ≠ app working.** Still required for a functioning app: run the Liquibase
migrations into the (empty) RDS, deploy the API + UI via `deploy-cloud.yml`, and set
`APP_ENV=production` on the task definition (see Follow-ups). Until the DB has a
schema, the ECS tasks fail their health check and the service won't stabilize.

## Follow-ups

- **Liquibase migration runner — DONE** (dedicated migration image `api/liquibase/Dockerfile`
  → `migrations-<tag>` in ECR via `build-images.yml`; `jsnotes-t2-migrations` task def +
  `jsnotes-t2-db-migration` secret in Terraform; `deploy-cloud.yml` runs it as a one-off
  `run-task` gated on exit 0). Not yet exercised end-to-end: the `migrations-<tag>` image
  is only built by `ecr-publish` (main/tag) or `preview` (PR), and `deploy-cloud.yml` is
  `workflow_dispatch`-only on a branch not yet on `main` — so a full run happens at cutover.
- Remove the temporary branch triggers before merging to `main`: the `push`
  trigger in `infra-cloud.yml` and the `feat/cloud-migration` branch in
  `ecr-publish.yml` (added so the cloud stack can be built/exercised off-branch
  before cutover).
- TLS phase needs `Route53` + `ACM` permissions (request from admin).
- SES is deferred — email-OTP sign-in is non-functional in the cloud env until added.
- `APP_ENV=production` in the ECS task definition — deferred; required before real
  auth (default `dev` enables placeholder/phantom-user auth). See the api
  `auth/dependencies.py` gate.
- **Approval gate** for the real prod apply: attach the `apply` job to a GitHub
  `Environment: production` with required reviewers, so apply pauses for human
  plan review (the destructive-guard is automated, not a human gate).
- Preview v2: see [`preview-v2.md`](preview-v2.md) (open decisions A/B/C; needs
  the Liquibase migration runner).

### Carried-over from the PR #79 review (legacy stack)
These were raised on the merge PR and apply to the **legacy EC2/compose** stack;
the cloud stack already resolves their substance:

- **Open SSH (`0.0.0.0/0:22`)** on the prod + preview EC2 (`terraform/modules/docker_host`)
  — a live exposure until cutover. Worth restricting now (separate `ssh_cidr_blocks`
  or SSM). The cloud stack has no SSH (Fargate + ECS Exec). *Worth fixing on the legacy stack.*
- **Fake destructive guard** in `infra-prod.yml` (`-detailed-exitcode` only) —
  the cloud stack's `infra-cloud.yml` has a real `terraform show -json` guard.
- **Auto-deploy path filter** (legacy `deploy.yml`/`ecr-publish.yml` miss
  compose/proxy changes) — moot in the cloud model (task def + S3 sync).
- **Russian comments in infra** — all new cloud code is English; legacy files still mixed.
