# Preview environments v2 — design

> **Status:** live. Shared layer (`terraform/preview-cloud` +
> `modules/preview-shared`): own VPC (no NAT — VPC endpoints, see decision D),
> ECS/ALB/RDS/S3/CloudFront + shared main-api. Per-PR `preview.yml` (ui/api repos)
> implemented. Supersedes the per-PR EC2+compose preview. Part of the cloud-native
> migration (`docs/aws-cloud-migration.md`, `larchanka-training/js-notebook`#110).
>
> **DB model — option B (shared `preview_main`).** Each PR gets its own API
> container, but all per-PR API services point at the one shared `preview_main`
> database — there is **no per-PR `pr_<N>` database** (yet). Consequence:
> **schema-changing API PRs are not fully previewed** — their migrations would
> alter the shared DB, so a per-PR DB (option A) is a deferred follow-up. The
> option-A design below is kept as the target for that follow-up; sections are
> marked **(option A — not yet built)** where they describe it.

## Goal

A per-PR preview that beats **both** existing approaches:

- **T1** (`dmc-1-t1-notebook-ui` `preview.yml`): per-PR **static frontend** in a
  shared S3+CloudFront under `/pr-<N>/`, API pointing at a shared **dev** backend.
  Cheap and fast, but previews only the frontend, shares one backend + one DB,
  and requires a persistent dev environment.
- **Current T2** (`terraform/preview`): a full **per-PR EC2 + docker-compose**
  stack (api+ui+postgres+proxy). Full isolation, but slow (~5 min boot),
  expensive (a whole EC2 per open PR), and more moving parts.

**v2** gives each PR its own backend at low cost/speed by sharing the heavy
resources and giving each PR only a thin slice. The database is **shared**
(`preview_main`, option B) — per-PR DB isolation (option A) is the target but not
yet built.

| Criterion | T1 | Current T2 | **v2 (now)** |
| --- | --- | --- | --- |
| Cost / PR | very low | high (EC2) | low (a small Fargate task) |
| Speed | seconds | ~5 min | ~1 min |
| Frontend per PR | ✅ | ✅ | ✅ |
| Backend per PR | ❌ (shared dev) | ✅ | ✅ |
| DB per PR | ❌ (shared) | ✅ | ❌ (shared `preview_main`; `pr_<N>` is option A, deferred) |
| Persistent dev backend needed | yes | no | a small shared preview layer |
| Complexity | low | medium | higher |

## Architecture

Split into a **shared layer** (persistent, shared by all PRs) and **per-PR
resources** (created/destroyed per PR).

```
                       CloudFront (preview)
                       /pr-<N>/*         → S3  (static UI under /pr-<N>/)
                       /pr-<N>/api/v1/*  → ALB → rule(PR N) → Fargate svc pr-<N> → shared RDS preview_main
shared:   ECS cluster · ALB · RDS (preview_main) · CloudFront · S3 bucket
per-PR:   image *-pr-N · Fargate service preview-pr-N · target group + ALB rule · S3 prefix /pr-N/
          (per-PR db pr_N is option A — not yet built)
```

### Shared layer (Terraform, persistent)

Two cost options:

| Option | Shared resources | Always-on cost | Risk |
| --- | --- | --- | --- |
| **Dedicated** (clean) | separate preview ECS cluster + ALB + RDS + CloudFront + S3 | ALB (~$18) + RDS (~$15) ≈ **$30/mo** | previews isolated from prod |
| **Reuse-prod** (cheap) | prod cluster/ALB/RDS, separate CloudFront+S3 only | ~$0 extra | a broken preview / heavy migration can hit **prod RDS/ALB** |

**Recommended: dedicated** — a faulty preview backend or migration must not be
able to affect prod. The ~$30/mo is the price of per-PR backend+DB isolation
(T1 pays it as a dev env; the current T2 pays per-PR EC2 instead).

### Per-PR resources (created by CI, destroyed on PR close)

For PR #42:
- ECR images `api-pr-42`, `ui-pr-42`.
- ECS Fargate service `preview-pr-42` on the shared cluster (image `api-pr-42`,
  `DATABASE_URL` → the shared `preview_main`).
- ALB target group + listener rule routing this PR to its service.
- S3 prefix `/pr-42/` (static UI).
- A sticky PR comment with `https://<cf>/pr-42/`.

A per-PR `pr_42` database (option A) is **not** created — see "Per-PR database"
below.

## Routing (the hard part)

One CloudFront + one ALB must route a PR's traffic to its own backend, while the
app serves `/api/v1` (not `/pr-42/api/v1`). CloudFront behaviors are static, so
they use wildcard patterns (`/pr-*/api/v1/*` → ALB, `/pr-*/*` → S3) and the per-PR
distinction happens at the ALB. Three options:

- **3a — per-PR `API_PREFIX` (CHOSEN).** Run PR #42's backend with
  `API_PREFIX=/pr-42/api/v1`; the app serves its routes there. ALB routes **by
  path** `/pr-42/api/v1/*` → PR-42 target group; CloudFront just forwards (no
  rewrite). Clean, no hacks. **Verified** in `api/app/main.py`: all routers
  (`health`/`auth`/`notebooks`) are included with `prefix=settings.api_prefix`,
  so a multi-segment `API_PREFIX` mounts them at `/pr-42/api/v1/...`, and the TG
  health check is `/pr-42/api/v1/health` (under the prefix). Note: `/docs`,
  `/redoc`, `/openapi.json`, `GET /` are at fixed paths (not under the prefix) —
  irrelevant for preview.
- **3b — strip path + header.** A CloudFront Function rewrites `/pr-42/...` →
  `/...` and sets `X-Preview-PR: 42`; the ALB routes **by header**. The app is
  untouched, but it is more intricate.
- **3c — host-based (`pr-42.preview.<domain>`).** ALB routes **by host**;
  relative `/api/v1` works, no rewrite. Cleanest, but needs a **wildcard domain +
  wildcard ACM cert** (Route53/ACM permissions + a domain).

Without a domain, start with **3a** (if the app honors `API_PREFIX`) or **3b**.

## Per-PR database

**Current (option B — shared `preview_main`).** Per-PR API services all use the
one shared `preview_main` database — `DATABASE_URL` points at it, nothing is
created or dropped per PR. The shared schema is migrated once (by
`deploy-preview.yml`, `contexts=dev`), not per PR.

- A non-schema-changing PR previews correctly.
- A **schema-changing** PR (one that adds a Liquibase changeset) is **not** fully
  previewed: its migration is not applied to a private DB, and applying it to the
  shared `preview_main` would affect every other open PR. Such PRs need option A.

**Target (option A — per-PR `pr_<N>`, not yet built).** When implemented:

- **Create:** on PR open, connect to the shared preview RDS as master and
  `CREATE DATABASE pr_<N>` (idempotent).
- **Migrate:** run Liquibase `update` against `pr_<N>`.
- The PR's backend uses `DATABASE_URL=postgresql://…/pr_<N>`.
- **Drop:** on PR close, `DROP DATABASE pr_<N>` (terminate active connections first).

Option A gives isolation per PR (separate database) without a per-PR RDS instance
— cheap (storage only), logically isolated. It is a deferred follow-up.

## CI lifecycle

`on: pull_request [opened, synchronize, reopened, closed]`

**deploy** (open/sync/reopen) — current option B:
1. build `api-pr-N` / `ui-pr-N` → ECR;
2. register task def (image `api-pr-N`, `DATABASE_URL` → shared `preview_main`,
   `API_PREFIX=/pr-N/api/v1`);
3. create/update target group + ALB rule + ECS service `preview-pr-N`;
4. build UI `--base=/pr-N/` + API base `/pr-N/api/v1` → `s3 sync → /pr-N/` → CloudFront invalidation;
5. `wait services-stable` → sticky comment with the URL.

Under option B there is no per-PR `CREATE DATABASE` / Liquibase step — the shared
`preview_main` schema is migrated separately by `deploy-preview.yml`. Option A
would insert `CREATE DATABASE pr_N` + migrate before step 2 and `DROP DATABASE
pr_N` on teardown.

**teardown** (closed):
- delete service + target group + ALB rule → `s3 rm /pr-N/` → invalidation.

## Terraform vs imperative

- **`modules/preview-shared`** (Terraform) — the persistent shared layer
  (cluster/ALB/RDS/CloudFront/S3), applied once.
- **Per-PR — imperative from CI** (`aws ecs`, `aws elbv2`, `s3`; plus `psql` once
  option A lands), not a Terraform workspace per PR. The per-PR slice is ephemeral and is faster to
  create/destroy via CLI (the same way T1 syncs static); Terraform manages only
  the stable shared layer.

## Cost

- **Persistent:** preview ALB (~$18) + preview RDS (~$15) ≈ **$30/mo** (dedicated);
  ~$0 extra with reuse-prod.
- **Per PR:** a small Fargate task (~cents/day) + database storage (~0), removed on close.
- Cheaper per-PR than the current EC2 approach; more isolated than T1.

## Gotchas

- CloudFront behaviors are static → use **wildcard patterns** (`/pr-*/…`); per-PR
  distinction is on the **ALB** (path / header / host).
- ALB listener rules have a default limit (~100/listener) — fine for course-scale PR volume, but a ceiling.
- (option A, when built) `DROP DATABASE` requires terminating active connections first.
- The `API_PREFIX` option (3a) works only if the app mounts routes under it — **verify in `api`**.
- The target-group health check for PR #42 is per-PR (e.g. `/pr-42/api/v1/health`).

## Dependencies / when to build

- Requires the shared layer (ECS/ALB/RDS) → blocked by the **VPC quota** like the
  rest of the migration. **Design now, build after apply.**
- Option 3c (host-based) needs a domain + Route53/ACM permissions.
- The deferred **Liquibase migration runner** becomes required here.

## Decisions (accepted)

- **A — Shared layer: dedicated.** A dedicated preview ECS cluster + ALB + RDS +
  CloudFront + S3 (~$30/mo always-on). Preview runs unreviewed PR code +
  migrations and must not touch prod — especially the prod database. Cost
  fallback if needed: reuse the prod **cluster + ALB** but keep a **separate
  preview RDS** (~$15/mo); **never** put preview databases in the prod RDS.
- **B — Routing: 3a (per-PR `API_PREFIX`).** Verified the app mounts all API
  routes under `settings.api_prefix` (`api/app/main.py`), so path-based ALB
  routing works with no CloudFront rewrite and no domain. Fall back to 3b (header)
  only if this ever stops holding; 3c (host) once a domain + Route53/ACM exist.
- **C — Per-PR: imperative from CI.** `aws ecs`/`elbv2`/`psql`/`s3` for the
  ephemeral per-PR slice; Terraform only for the stable shared layer. Add an
  orphan **sweep** (tag preview resources, periodically destroy stale ones) to
  guard against failed teardowns.
- **D — Egress: VPC endpoints, no NAT (no Elastic IP).** The preview VPC is
  created with `create_nat = false` (a new flag on `modules/network`; prod keeps
  the default `true`). The regional **Elastic IP limit was exhausted** (17/17,
  all attached to NAT gateways — `apply` failed on `AllocateAddress →
  AddressLimitExceeded`), and a NAT requires an EIP. Instead, private-subnet
  egress to the AWS services preview needs goes through **VPC endpoints**
  (`modules/preview-shared/endpoints.tf`): **S3** (gateway, free), **ECR api +
  dkr**, **Secrets Manager**, **CloudWatch Logs** (interface). RDS is in-VPC, so
  no endpoint. Trade-off: preview tasks have **no arbitrary-internet egress** —
  fine, since they only need AWS services (images/secrets/logs/DB); an external
  call would go via a backend proxy or a (re-added) NAT once an EIP is available.
  Cost ≈ NAT (~4 interface endpoints), but unblocked without the admin quota bump.

## Networking note (NAT vs VPC endpoints)

`modules/network` takes `create_nat` (default `true`). Prod (`terraform/cloud`)
keeps a NAT + EIP (general internet egress). Preview (`terraform/preview-cloud`)
sets it `false` and adds VPC endpoints — no Elastic IP, more locked down (tasks
can't reach the open internet), same cost ballpark. If preview ever needs
arbitrary outbound, flip `create_nat = true` (needs a free EIP / raised quota).

These are the accepted choices; implementation followed once the cloud stack was
applied (the VPC quota, then the Elastic-IP limit, were the gating constraints).
