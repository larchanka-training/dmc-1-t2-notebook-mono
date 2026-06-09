# AWS cloud-native migration

Migration of T2 from a single EC2 + docker-compose prod to a cloud-native stack on
AWS (ECS Fargate + RDS + S3/CloudFront). Tracked as a single umbrella task:
`larchanka-training/js-notebook`#110. **Done and live on `main`** — the cloud stack
is now the only production infrastructure; the legacy EC2 stack has been removed.

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

The cloud stack is the only production infrastructure.

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

- **pull_request** (paths `terraform/cloud/**`,
  `terraform/modules/{network,backend,frontend,data}/**`,
  `.github/workflows/infra-cloud.yml`) → `init` + `validate` + `plan` (read-only),
  posted as a sticky PR comment for review.
  All four modules the cloud stack composes trigger the plan gate, not just network.
- **push to `main`** (same paths) → auto-`apply` + write-once init of the auth
  secrets (see "Infra auto-applies on merge" below).
- **workflow_dispatch** → `plan` or `apply` (+ `allow_destroy`) for manual runs.
- **Destructive-change guard:** parses `terraform show -json` and fails the run
  if the plan would `delete`/replace any resource, unless `allow_destroy=true`
  on a manual dispatch. This is a real guard, unlike a bare `-detailed-exitcode`,
  and it gates the auto-apply path too.

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
migrations into the (empty) RDS and deploy the API + UI via `deploy-cloud.yml`. Until
the DB has a schema, the ECS tasks fail their health check and the service won't
stabilize. The task definition sets `APP_ENV=production` (see Follow-ups), so
protected endpoints return `501 AUTH_NOT_IMPLEMENTED` until real auth lands — the
public URL never runs the dev placeholder auth.

## Bedrock / AI inference access (#113)

The backend reaches AWS Bedrock (Amazon Nova) over a **private** path with a
**least-privilege IAM** grant and **metadata-only** logging. Bedrock is a managed,
account+region-scoped service — there is no model "instance" to deploy or expose;
access is gated entirely by IAM, and the network path is kept private with a VPC
interface endpoint. Design: [`ai-architecture.md`](ai-architecture.md).

**Models (decided).** Generation = **Nova Lite**, prompt-injection pre-filter =
**Nova Micro** — both the cheapest text Nova tier, both available in `eu-north-1`.
They are invoked through the **EU Geo cross-region inference profiles**
(`eu.amazon.nova-lite-v1:0` / `eu.amazon.nova-micro-v1:0`): Nova Micro has **no
In-Region** option in `eu-north-1`, so the Geo profile is the only path that works
for both. From `eu-north-1` the EU profile can route to
`eu-central-1, eu-north-1, eu-west-1, eu-west-3`.

**Terraform.**

| Where | What |
| --- | --- |
| `modules/backend/bedrock.tf` | Task-role IAM policy (`InvokeModel*` + `Converse*`) scoped to the two inference-profile ARNs **and** the foundation-model ARN in each of the 4 routed regions (cross-region inference is denied without the latter). Plus account-wide model-invocation logging to CloudWatch with **`text/image/embedding_data_delivery_enabled = false`** — prompt/completion bodies never reach CloudWatch (`ai-architecture.md` §8.5); only metadata is logged. |
| `modules/network/bedrock_endpoint.tf` | `bedrock-runtime` **interface VPC endpoint** (PrivateLink), `private_dns_enabled`, SG allows 443 from the ECS SG only. Shared by **both** the prod and preview stacks (both instantiate `modules/network`). In preview (no NAT) this is the only path to Bedrock. |
| `modules/preview-shared/bedrock.tf` | Mirrors the task-role grant for the preview task role (per-PR API). Does **not** declare the logging config — that singleton is owned by the prod stack. |
| `modules/backend` env, `modules/preview-shared` main-api | `LLM_BEDROCK_REGION`, `LLM_BEDROCK_GENERATOR_MODEL_ID`, `LLM_BEDROCK_GUARD_MODEL_ID` injected as non-secret env (names match the backend contract for #117/#118; single source: the model-id variables feed both the IAM policy and the runtime env). |

**No Bedrock API key.** Bedrock authenticates via the **task IAM role** — there is
no key/secret to store, rotate, or leak. The `*_data_delivery=false` logging
contrasts with team T1, who log full prompt/response bodies in prod.

**Cross-stack notes.**
- The `aws_bedrock_model_invocation_logging_configuration` resource is **one per
  account/region**; only the prod stack declares it. Adding it to preview too would
  make the two stacks fight over the same singleton.
- The **per-PR** preview API task definitions are built imperatively by CI (api
  repo `preview.yml`) by **deriving from the shared main-api task def** via
  `describe-task-definition` + `jq` (swap image, append `API_PREFIX`) — the jq
  **preserves the existing `environment`**. Since the `LLM_BEDROCK_*` vars live on
  the main-api task def (above) and `deploy-preview.yml` also preserves env on
  image swaps, the per-PR task defs **inherit `LLM_BEDROCK_*` automatically** — no
  `preview.yml` change is needed. (Only a rewrite that rebuilds the task def from
  scratch instead of deriving would break this.)
- Prod gates protected endpoints behind `501 AUTH_NOT_IMPLEMENTED` until real auth
  lands, so the LLM endpoint is exercised and smoke-tested in **preview**, not prod.
- **Cost — decision (prod endpoint is an accepted trade-off).** An interface
  endpoint is a standing per-AZ ENI charge (~$15/mo per endpoint over 2 AZs).
  Preview has **no NAT**, so its endpoint is mandatory — the only path to Bedrock.
  Prod **has** a NAT, so it *could* reach Bedrock through it instead. **We keep the
  prod endpoint anyway** (~$15/mo): NAT egress traverses the public internet to
  Bedrock's public endpoint, which would violate issue #113's "accessible only
  from the private internal network" criterion. Dropping the prod endpoint is the
  only way to save that ~$15/mo, and it is **rejected** on that basis.

**Smoke test** (after apply): see
[`bedrock-smoke-test.md`](bedrock-smoke-test.md) — a one-off ECS task from inside a
private subnet that calls Nova via the endpoint, proving IAM + endpoint + model
access end-to-end before the application endpoint is deployed.

**Cost guardrail — deferred (needs an admin decision + permission).** A monthly
AWS Budget alert on Bedrock spend was attempted in Terraform but **`deploy-user`
lacks `budgets:ModifyBudget`** (budgets are account-level; the deploy role is not
granted them on the shared course account). Rather than block this PR, the budget
is left out. Open item for the account admin: (a) decide whether a per-account
Bedrock budget is wanted, and (b) if so, either grant `deploy-user`
`budgets:Modify/ViewBudget` so it can be managed in `terraform/cloud`, or create
it centrally. Caveat to weigh: on the shared account a `Service = Amazon Bedrock`
filter is account-wide (all teams), so any threshold is an early warning, not a
T2-only figure. Meanwhile the first line of defence is the app-level rate limit
(20 req/min/user, the backend owner's #118); a finer token ceiling stays open
(`ai-architecture.md` §9).

## Follow-ups

- **Liquibase migration runner — DONE** (dedicated migration image `api/liquibase/Dockerfile`
  → `migrations-<tag>` in ECR via `build-images.yml`; `jsnotes-t2-migrations` task def +
  `jsnotes-t2-db-migration` secret in Terraform; `deploy-cloud.yml` runs it as a one-off
  `run-task` gated on exit 0). Not yet exercised end-to-end: the `migrations-<tag>` image
  is only built by `ecr-publish` (main/tag) or `preview` (PR), and `deploy-cloud.yml` is
  `workflow_dispatch`-only on a branch not yet on `main` — so a full run happens at cutover.
- **Cutover done.** The temporary off-branch triggers were removed: `deploy-cloud.yml`
  and `deploy-preview.yml` dropped their `push` triggers + `build` jobs. **Prod
  deploy is automatic** — `deploy-cloud.yml` runs on `workflow_run` after **ECR
  Publish** succeeds on `main` (image tag from the build's `head_sha`), plus
  `workflow_dispatch` for manual deploy/rollback. `deploy-preview.yml` follows
  the same shape (`workflow_run` after ECR Publish + `workflow_dispatch`), so the
  shared preview backend tracks `main` automatically. Images come from
  `ecr-publish.yml` (main/tags).
- **Infra auto-applies on merge (GitOps).** Both `infra-cloud.yml` (prod) and
  `infra-preview-cloud.yml` (preview shared layer) are `pull_request` (plan) +
  **`push` to `main` (auto-apply)** + `workflow_dispatch`. On a PR the `plan` is
  posted as a sticky PR comment, so the **required reviewers approve the real plan,
  not just the code diff** — that PR approval *is* the human gate, so no separate
  GitHub Environment approval gate is used. The destructive-change guard still
  blocks any delete/replace on the auto-apply path (requires a manual dispatch with
  `allow_destroy=true`) and re-runs at apply time, so drift between PR and merge
  can't slip a destructive change through. Apply-on-merge — not on PR open — so an
  unmerged PR never mutates shared/prod infra.
- **Task definition has a single owner: Terraform.** Both `deploy-cloud.yml`
  (prod) and `deploy-preview.yml` (shared preview main-api) render each release
  from the **Terraform-registered baseline revision** (read via
  `terraform output` from state: `api_task_definition_arn` /
  `migration_task_definition_arn`, preview: `main_api_task_definition_arn`),
  swapping only the image — never from the live service's latest family
  revision. This kills the env-drift class of bug where pipeline revisions
  inherited a stale `environment` from pre-IaC revisions for weeks (the
  silent-rollback incident). The prod read retries while infra apply is still
  writing state — a soft barrier ordering deploy after apply on mixed infra+app
  merges. Both deploys also **fail red on a circuit-breaker rollback**: after
  `services-stable` they verify the registered revision is the one actually
  serving (a rollback otherwise looks like a green deploy on stale code). The
  per-PR API slices (`api` repo `preview.yml`) still render from the live
  family — mirroring this discipline there is a follow-up in the `api` repo.
- **Auth secrets are auto-initialized (write-once).** Terraform creates the
  `jwt-secret` / `otp-hash-secret` containers (prod: `jsnotes-t2-*`, preview:
  `jsnotes-t2-preview-*`; values never in code or state); after each apply the
  infra workflow generates a random value for any container that has **no value
  yet** (`openssl rand`, 64 chars) and never overwrites an existing one — so
  rotation done in AWS stays authoritative, nobody ever handles the values, and
  no manual bootstrap step exists. The preview main-api gets the same secrets
  wired for prod parity even though `APP_ENV=dev` does not require them.
- **Release-ordering rule (expand/contract).** Infra and app pipelines stay
  separate (different cadence/risk), so changes that span both must be
  backward-compatible per step: land + apply the infra capability (e.g. a new
  secret with a value) **before** merging app code that *requires* it. Never
  merge a change where the new app revision cannot boot on the currently-applied
  infra — ordering between the two pipelines is deliberately not guaranteed
  beyond the soft barrier above.
- TLS phase needs `Route53` + `ACM` permissions (request from admin).
- SES is deferred — email-OTP sign-in is non-functional in the cloud env until added.
- **`APP_ENV=production` — DONE.** The ECS task definition's `environment` block is
  rendered from the `app_environment` map var (`terraform/modules/backend`), which
  defaults to `{ APP_ENV = "production" }` and is validated so APP_ENV can't be
  dropped or set to a garbage value. So the dev-only placeholder X-User-Id auth is
  disabled on the public URL: protected endpoints return `501 AUTH_NOT_IMPLEMENTED`.
  Add further non-secret env (LOG_LEVEL, CORS_*, …) as keys in that map; secrets go
  through Secrets Manager. See the api `auth/dependencies.py` gate.

  **Boot requirement (not deferrable):** under `APP_ENV=production` the api
  `config.py` validator fail-fasts on startup unless **`JWT_SECRET`** and
  **`OTP_HASH_SECRET`** are both set to a non-default value of >= 32 chars. So
  these two are required for the task to *boot at all* — independent of whether
  real (non-501) auth is enabled. They are created as Secrets Manager containers
  in `terraform/modules/backend` and injected via the task definition's `secrets`
  block; their values are **auto-initialized write-once** by `infra-cloud.yml`
  after apply (generated, never stored in Terraform code/state, never
  overwritten once set).

  **Checklist — everything that must exist before the API can serve real
  (non-501) auth:**
  - [ ] **SES** verified + sending (email-OTP delivery).
  - [x] **`JWT_SECRET`** + **`OTP_HASH_SECRET`** in Secrets Manager, injected into
    the task definition (also a hard boot requirement, see above).
  - [ ] **Refresh-token store** (rotation/revocation) backing the JWT flow.
  - [ ] **Rate-limit** on the OTP-request / token endpoints (brute-force guard).
  - [ ] Remove the prod dev-seed row once real users exist.

  Only when all of the above are in place does the placeholder gate get replaced by
  the real OTP→JWT flow; `APP_ENV` stays `production` throughout.
- **Approval gate** for the real prod apply: attach the `apply` job to a GitHub
  `Environment: production` with required reviewers, so apply pauses for human
  plan review (the destructive-guard is automated, not a human gate).
- Preview v2: see [`preview-v2.md`](preview-v2.md) (open decisions A/B/C; needs
  the Liquibase migration runner).
