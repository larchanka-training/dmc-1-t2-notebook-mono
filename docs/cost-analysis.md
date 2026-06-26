# JS Notebook — Cost Analysis (AWS, Bedrock, Storage, Traffic)

**Author:** Engineer #2 (Cost Optimization), team T2
**Scope:** estimate the monthly cost of running JS Notebook on AWS at 100 /
1,000 / 10,000 users, across production *and* the always-on preview/dev
layer, broken down by AWS infrastructure, Amazon Bedrock, storage, and
traffic — with explicit assumptions and fixed-vs-variable cost separation.

> **Snapshot metadata.** Analysis date 2026-06-24. Terraform/code read at
> `main` commit `1ad66a5` (this branch, `t2-153-cost-optimization`, rebased
> on top of it). Supersedes the original analysis read at commit `51ca426`
> (this PR's original base). Related PRs since that base, all now reflected
> below: `larchanka-training/dmc-1-t2-notebook-mono#153` (CloudWatch alarms +
> SNS + dashboard), `#155` (the RDS Multi-AZ / ECS autoscaling PR that this
> report's §1.6/§10 cite — see the correction there), `#158` (on-demand SSM
> bastion, default-off), `#169` (analytics CloudWatch metric filters +
> second dashboard — the dashboard's first `terraform apply` failed
> validation, but the roll-forward fix (`1ad66a5`) merged to `main` and its
> own `infra-cloud.yml` apply succeeded; both dashboards are now live —
> see §1.6). Because pricing and infra both move fast, re-check this
> snapshot line before trusting any number here more than a few weeks old.

> **Read this first.** This report intentionally separates *confirmed*
> numbers (read from this repo's Terraform/application code, or from a
> live AWS pricing page) from *estimated* numbers (industry-standard list
> prices with a documented regional uplift, because several AWS pricing
> pages would not render region-filtered tables through automated fetch
> tools in this session). Every price in §11.1 is tagged **[confirmed]** or
> **[estimate]**. Before this analysis is used for a real budget decision,
> the **[estimate]** rows must be re-verified against the AWS Pricing
> Calculator (calculator.aws) for `eu-north-1`, and the placeholder UI
> bundle size (§7.1) must be replaced with Engineer #3's actual measurement.

---

## 1. Executive summary

1. **Fixed infrastructure dominates at small-to-medium scale, not Bedrock.**
   At the baseline usage profile, total estimated production cost moves from
   **~$130/mo at 100 users to ~$189/mo at 10,000 users** — a 100x increase in
   users produces only a ~46% increase in cost, because ~$119–161/mo of prod
   cost (RDS Multi-AZ, NAT Gateway, ALB, the Bedrock VPC endpoint, the
   2-task Fargate floor) is paid 24/7 regardless of how many users actually
   show up. The product is currently **infrastructure-cost-insensitive to
   user count** up to roughly the low-thousands.
2. **Bedrock (Amazon Nova Lite + Nova Micro) is cheap at realistic usage.**
   Even at the *heavy* usage profile and 10,000 users, aggregate legitimate
   Bedrock spend is **~$540/mo** (§7). Nova Lite/Micro on-demand pricing is
   low enough that LLM generation is not the primary cost driver at any
   scale modeled here.
3. **The real Bedrock cost risk is per-user abuse, not aggregate volume.**
   There is no per-day or per-month token/request ceiling in the code — only
   a 20 req/min/user limiter, and it is **in-process (non-distributed)**, so
   it is enforced independently by every one of the 2–6 autoscaled API
   replicas. A single user sustaining the per-minute cap continuously for a
   month, hitting max retries and max token ceilings every time, can drive
   **up to ~$2,013/mo alone — or up to ~$12,080/mo if requests land on all 6
   replicas** (§7.2). This single missing control is a bigger cost exposure
   than any legitimate-usage scenario in this report.
4. **The preview/dev environment costs about as much as production.**
   The shared preview layer's fixed floor is **~$119/mo** — almost
   identical to prod's fixed floor — even though it serves no paying users.
   Its no-NAT design (5 VPC interface endpoints instead of 1 NAT Gateway,
   forced by an exhausted Elastic IP quota, not chosen for cost) is actually
   **~$40/mo more expensive in fixed terms** than a NAT Gateway would have
   been, and only becomes cheaper than NAT if outbound data volume would
   have exceeded **~890 GB/month** (§4.7) — unlikely for a dev/preview
   environment.
5. **Storage is a rounding error in every scenario except one.** Notebook
   `cells` JSONB storage stays under ~$5/mo of RDS storage at 10,000 users
   for low/baseline usage. But at the **heavy profile + 10,000 users**, 12
   months of unpurged notebook history (notebooks are soft-deleted, never
   physically removed — no purge job exists) reaches **~206 GB**, which
   **exceeds the Terraform-configured `max_allocated_storage = 100 GiB`
   autoscale ceiling** for prod RDS (§6, §10). This is the one scenario in
   this report where infrastructure as currently configured would not
   simply "scale" — it would hit a hard ceiling.
6. **Monitoring now exists, and it's still cost-trivial — both dashboards
   are live.** As of this snapshot, `terraform/` has 5 CloudWatch alarms (4
   ALB/ECS + 1 external Route 53 health check) with 2 SNS topics, the
   `jsnotes-t2` CloudWatch dashboard (PR `dmc-1-t2-notebook-mono#153`,
   merged 2026-06-19), and 4 log-metric-filter custom metrics plus the
   `jsnotes-t2-analytics` dashboard for product analytics (PR #169, merged
   2026-06-23) — all of it live and emitting. `jsnotes-t2-analytics`'s
   first `infra-cloud.yml` `terraform apply` on `main` after #169 merged
   failed validating `aws_cloudwatch_dashboard.analytics`: every widget in
   `terraform/modules/backend/analytics.tf` omitted the `region` property
   that AWS's `PutDashboard` requires, unlike the working `jsnotes-t2`
   dashboard in `terraform/cloud/monitoring.tf`, which sets `region`
   explicitly on every widget. The roll-forward fix (commit `1ad66a5`,
   adding `region = var.aws_region` to every widget) merged to `main`, its
   own `infra-cloud.yml` apply succeeded, and the dashboard is now live —
   see §4.4. This never moved the dollar figure either way: a 2nd vs. 1st
   dashboard is still $0, under the 3-free-per-account tier. Combined
   monthly cost of what's deployed is **≈$2.20/mo** — alarms/dashboards/
   metrics at this volume round to noise next to the ~$119–161/mo fixed
   floor. *Correction to an earlier version of this report:* §10 used to
   cite commit `5d88636` (whose message was titled "...CloudWatch alarms")
   as a PR that "claimed alarms but didn't ship them." That commit was
   itself superseded, within the same branch, by a later commit explicitly
   deferring observability to a separate PR — the actual merged PR #155
   never claimed to ship alarms. Observability shipped for real in the
   follow-up PR `dmc-1-t2-notebook-mono#153` referenced above.

---

## 2. Architecture cost map

| Environment | Always-on? | Scales with users? | Owns |
|---|---|---|---|
| **Production** (`terraform/cloud`) | Yes, 24/7 | Partially (ECS autoscale 2→6, RDS storage, CloudFront/ALB traffic) | ECS Fargate API, ALB, RDS PostgreSQL (Multi-AZ), NAT Gateway, Bedrock VPC endpoint, S3+CloudFront (UI), CloudWatch logs, ECR images |
| **Preview shared layer** (`terraform/preview-cloud`) | Yes, 24/7 | No — fixed regardless of dev/QA activity | Shared ALB, RDS (Single-AZ), main-api Fargate task, 5 VPC interface endpoints (no NAT), shared S3+CloudFront |
| **Per-PR preview slice** (`api/.github/workflows/preview.yml`) | Only while a PR is open | Scales with **open PR count**, not end users | One more 256 CPU/512 MiB Fargate task per open PR, on the shared ALB/CloudFront (no extra ALB/CDN cost) |
| **Dev/local** | No | N/A | Developer's own machine — $0 AWS cost (Docker Compose) |

All resource specs below were read directly from this repo's Terraform at
`main` commit `3d23566` (see snapshot metadata above), via analysis of
`terraform/cloud`, `terraform/preview-cloud`, and
`terraform/modules/{backend,data,network,frontend,preview-shared,bastion}`.

| Component | Prod | Preview shared | Notes |
|---|---|---|---|
| ECS Fargate API | 256 CPU / 512 MiB, autoscale **min 2 / max 6**, target 70% CPU | 256 CPU / 512 MiB, fixed `desired_count=1`, **no autoscaling** | No Fargate Spot used anywhere |
| ALB | 1, always-on | 1, shared by main-api + every per-PR slice | No WAF on either |
| RDS PostgreSQL 16 | `db.t3.micro`, **Multi-AZ=true**, 20 GiB gp3 (autoscale ceiling **100 GiB**), 14-day backups, Performance Insights (free tier), Enhanced Monitoring 60s, deletion protection | `db.t3.micro`, **Multi-AZ=false**, 20 GiB gp3, 1-day backups, no PI/monitoring, no deletion protection | One shared preview DB, not per-PR |
| NAT Gateway | **1** (single AZ) | **0** — blocked on exhausted EIP quota (17/17), replaced by VPC endpoints | Documented in `aws-cloud-migration.md` as a deliberate trade-off |
| VPC interface endpoints | `bedrock-runtime` only, 2 AZs | `bedrock-runtime` + `ecr.api` + `ecr.dkr` + `secretsmanager` + `logs`, all 2 AZs each (10 ENIs) | Repo's own docs cost the Bedrock endpoint at "~$15/mo per endpoint over 2 AZs" — confirmed against current PrivateLink pricing |
| CloudWatch | API/migration/Bedrock-metadata log groups, **14-day retention**; **5 alarms, 2 SNS topics, 2 dashboards live, 4 metric filters** (PR `dmc-1-t2-notebook-mono#153` + #169) | Shared log group, **7-day retention**; no alarms/dashboards | Monitoring (`dmc-1-t2-notebook-mono#153`) + analytics (#169) both shipped after this report's original base and are now both live, see §4.4 |
| S3 (UI) | 1 bucket, versioning **on**, **no lifecycle rule** | 1 bucket, versioning **off**, **no lifecycle rule** | Old object versions in prod accrue forever |
| CloudFront | 1 distribution, `PriceClass_100` (NA+EU only) | 1 distribution, `PriceClass_100` | API paths are 100% cache-miss by design |
| ECR | Repository exists **out-of-band** (not in Terraform), **no lifecycle policy found anywhere** | — | Images accumulate indefinitely; flagged as an unbounded, untracked cost driver |
| Bastion (EC2) | `t3.nano`, **default-off** (`create_bastion=false`, `count = 0`) | — (prod-only module) | On-demand SSM tunnel for DB access (PR #158); $0 while disabled, no persistent resource created |

---

## 3. Assumptions

This report does not pretend false precision. All user-activity numbers
below are **assumptions**, not measurements — there is no production
traffic history for this project yet. Three usage profiles are modeled
across all three user counts, so each scenario is really a 3×3 grid (9
points), not 3 single numbers.

| Parameter | Low | Baseline | Heavy |
|---|---|---|---|
| Active days/user/month | 5 | 10 | 18 |
| AI (`/llm/generate`) requests/active day | 1 | 3 | 8 |
| Avg. prompt tokens | 500 | 800 | 1,500 |
| Avg. completion tokens | 200 | 300 | 600 |
| Avg. notebook size | 50 KB | 100 KB | 300 KB |
| Notebooks created/user/month | 0.5 | 1.0 | 3.0 |
| Sessions/active day | 1 | 2 | 4 |
| Effective generator calls/request (retries) | 1.05× | 1.2× | 1.5× |

**Cell-run frequency is deliberately omitted from the cost model.** Per
`AGENTS.md` §1 and confirmed in code (`enable_execute: bool = False` in
`api/app/core/config.py`), cell execution runs **client-side in a QuickJS/
WASM sandbox in the browser**. The backend Execution Worker described in
`docs/execution-architecture.md` is a future path and is disabled in
production today. **Cell runs currently generate $0 AWS cost** — they never
reach the backend. If/when server-side execution ships, this report's
traffic and compute model would need a new line item; see §10.

**Retry-rate assumption.** The generator (`eu.amazon.nova-lite-v1:0`) retries
on syntax-validation failure, capped at `LLM_VALIDATION_MAX_RETRIES=2` (max 3
total generator calls/request) — confirmed in
`api/app/modules/llm/services/generation_service.py`. There is no telemetry
on actual retry frequency in the codebase, so the "effective calls/request"
multipliers above (1.05×/1.2×/1.5×) are this report's own assumption, not a
measured rate.

**Notebook accumulation.** Notebooks are soft-deleted (`deleted_at` column)
with **no purge job found** in the codebase — storage is modeled at a
12-month accumulation snapshot (`notebooks_created_per_user_per_month × 12`)
to represent realistic steady-state growth, not month-1 storage.

**Guard-call token assumption.** The guard model
(`eu.amazon.nova-micro-v1:0`) is invoked unconditionally once per generate
request, with a structurally-bounded prompt (fixed system prompt + task ≤
8,000 chars + ≤ 3 context cells × ≤ 500 chars). This report assumes a
**typical** (not worst-case-ceiling) guard prompt of ~600 input / ~20 output
tokens across all profiles, since the hard caps in code bound guard input
regardless of how "heavy" overall usage is. The worst-case ceiling is used
separately in §7.2's abuse scenario.

**Environment assumptions.** Production cost is computed per the 3×3 usage
grid above. The preview shared layer and per-PR slices are **not** a
function of end-user count — they are modeled separately, driven by
developer/CI activity (§4.7). Local/dev cost is the developer's own machine,
not AWS — $0.

**UI bundle size — placeholder, pending Engineer #3.** §7.1's CloudFront
traffic model uses an assumed 1.2–1.5 MB gzipped initial bundle. This is a
**placeholder**; Engineer #3's bundle-size analysis is the authoritative
input here and should replace this number before final submission.

---

## 4. AWS infrastructure cost breakdown

All Fargate/RDS/ALB figures below assume `eu-north-1` (the project's actual
region). Pricing methodology and confirmed-vs-estimated sourcing is in
§11.1.

### 4.1 Production — fixed, always-on (independent of user count)

| Component | Configuration | Monthly cost | Fixed/variable |
|---|---|---|---|
| ECS API (Fargate) | 256 CPU/512 MiB × 2 tasks (autoscale floor) | **$20.72** | Fixed floor; **$62.17** at max autoscale (6 tasks) |
| ALB | 1, 730 hrs/mo, base hourly charge | **$20.97** | Fixed (+ LCU-hours, negligible at this volume — see §4.3) |
| RDS instance | `db.t3.micro`, Multi-AZ | **$30.22** | Fixed (storage scales with data — see §6) |
| NAT Gateway | 1, single AZ | **$32.85** | Fixed (+ $0.045/GB processed — negligible at this volume) |
| Bedrock VPC endpoint | `bedrock-runtime`, 2 AZs | **$14.60** | Fixed (+ $0.01/GB processed — negligible; Bedrock payloads are KB-sized JSON) |
| **Prod fixed floor (excl. storage/CDN/CW/ECR)** | | **≈ $119.37/mo** | |
| **Prod fixed ceiling (max autoscale)** | | **≈ $160.81/mo** | |

### 4.2 Preview shared layer — fixed, always-on, NOT user-count-driven

| Component | Configuration | Monthly cost |
|---|---|---|
| ALB | 1, shared by main-api + all per-PR slices | **$20.97** |
| RDS instance | `db.t3.micro`, Single-AZ | **$15.11** |
| Main-api Fargate | 256/512, 1 task, no autoscaling | **$10.36** |
| 5 VPC interface endpoints | `bedrock-runtime`, `ecr.api`, `ecr.dkr`, `secretsmanager`, `logs` × 2 AZs each | **$73.00** |
| **Preview fixed floor** | | **≈ $119.44/mo** |

### 4.3 Per-PR preview slice (driven by open-PR count, not users)

One 256/512 Fargate task per open PR, no extra ALB/CDN cost (shared
infra): **$10.36/mo if open the full month, or $0.345/day**. A PR open
for 2/5/10 days costs **$0.69 / $1.73 / $3.45** respectively. This scales
with team activity (PRs/week), not product users.

### 4.4 CloudWatch Logs, alarms, dashboards, metrics (variable + fixed-trivial)

**Logs.** Estimated at ~1.5 KB/request structured `structlog` JSON, 14-day
retention:

| Profile | 100 users | 1,000 users | 10,000 users |
|---|---|---|---|
| Low | $0.0015 | $0.015 | $0.15 |
| Baseline | $0.007 | $0.066 | $0.66 |
| Heavy | $0.027 | $0.265 | $2.65 |

Negligible at every scale modeled.

**Alarms, SNS, dashboards, metrics — shipped since this report's original
base, now priced explicitly.** PR `dmc-1-t2-notebook-mono#153` added 5
`aws_cloudwatch_metric_alarm` resources (4 ALB/ECS in `eu-north-1` + 1
Route 53 external-check alarm in `us-east-1`) and 2 SNS topics (email-only);
PR #169 added 4 `aws_cloudwatch_log_metric_filter` resources for product
analytics, all four deployed and emitting. Both CloudWatch dashboards
defined in Terraform are now live on AWS: `jsnotes-t2` (from
`dmc-1-t2-notebook-mono#153`) deployed cleanly; `jsnotes-t2-analytics`
(from #169) failed its first `terraform apply` (missing `region` on every
widget in `terraform/modules/backend/analytics.tf`), but the roll-forward
fix (commit `1ad66a5`) merged to `main` and its `infra-cloud.yml` apply
succeeded — see §1.6.

| Item | Quantity | Monthly cost | Status |
|---|---|---|---|
| CloudWatch alarms | 5 × $0.10/alarm-mo | **$0.50** | **[confirmed]** |
| Route 53 health check (external, basic) | 1 | **≈$0.50** | **[estimate]** |
| SNS email notifications | 2 topics, alert-volume only | **$0** (well under free tier) | **[confirmed]** |
| CloudWatch dashboards | 2 live (`jsnotes-t2`, `jsnotes-t2-analytics`) — ≤ 3 free/account | **$0** today | **[confirmed]** — a 3rd *live* dashboard would add $3/mo |
| Custom metrics from log-metric-filters | 4, deployed | **≈$1.20** ($0.30/metric-mo) | **[confirmed]** — billed from deploy time regardless of dashboard/alarm usage: each filter's `default_value = 0` guarantees a datapoint every period even with zero matching log events, so billing isn't contingent on anyone viewing a dashboard or an alarm referencing the metric |
| **Total, monitoring + analytics** | | **≈$2.20/mo** | Folded into §9 prod totals |

This doesn't move any total in §9 by more than a few cents, but it is now
a real, shipped, billed line item rather than the "doesn't exist" claim in
an earlier version of this report (§1.6).

### 4.5 ECR image storage (not user-count-driven — flagged risk)

No ECR lifecycle policy exists in the codebase or CI workflows. Images
accumulate indefinitely across 3 tag prefixes (`api-`, `ui-`,
`migrations-`) plus per-PR `-pr-<N>` tags, at $0.10/GB-month. This report
uses a flat **$8/mo placeholder estimate** (≈80 GB accumulated at a mature
point in the project) since actual accumulation depends on deploy
cadence, not user count — **this number should be replaced with a real
`aws ecr describe-repositories` + `list-images` size check**, not trusted
as computed. Recommend filing a dedicated follow-up issue (qualified
`owner/repo#NN` per `AGENTS.md` §11 once filed) to add an ECR lifecycle
policy — e.g. expire untagged images and cap image count per tag prefix
(`api-`, `ui-`, `migrations-`, `*-pr-<N>`) — which closes both this
cost-tracking gap and the unbounded-growth risk in §10.

### 4.6 S3 (UI hosting)

Negligible at every scale: a 5–10 MB SPA build, even with unpruned
version history accumulated over years, stays under $0.01–0.05/mo
(§11.2). Not modeled as a separate line in the totals below.

### 4.7 NAT vs. VPC-endpoint cost comparison (preview's no-NAT design)

Preview's 5 VPC interface endpoints cost **$73.00/mo** fixed vs. a single
NAT Gateway's **$32.85/mo** fixed — **$40.15/mo more**, before any data
is processed. The break-even point, where NAT's $0.045/GB data charge
would have caught up, is **≈892 GB/month** of outbound data — a volume a
dev/preview environment is unlikely to hit. This wasn't a cost decision
(the EIP quota was exhausted, 17/17 allocated, per `docs/preview-v2.md`
decision D) — but it is, today, the more expensive option at the preview
layer's actual traffic level.

---

## 5. Bedrock cost model

### 5.1 Formula

```text
monthly_ai_requests      = users × active_days × ai_requests_per_active_day
effective_generator_calls = monthly_ai_requests × retry_multiplier   (1.05–1.5×, §3)
guard_calls               = monthly_ai_requests                       (always exactly 1×, unconditional)

generator_input_tokens   = effective_generator_calls × avg_prompt_tokens
generator_output_tokens  = effective_generator_calls × avg_completion_tokens
guard_input_tokens       = guard_calls × guard_prompt_tokens (~600, structurally capped)
guard_output_tokens      = guard_calls × guard_completion_tokens (~20, typical — cap is 256)

generator_cost = (generator_input_tokens/1e6 × $0.06) + (generator_output_tokens/1e6 × $0.24)   # Nova Lite
guard_cost     = (guard_input_tokens/1e6 × $0.035)    + (guard_output_tokens/1e6 × $0.14)         # Nova Micro

bedrock_cost = generator_cost + guard_cost
```

Models confirmed in `api/app/core/config.py`:
`llm_bedrock_generator_model_id = "eu.amazon.nova-lite-v1:0"`,
`llm_bedrock_guard_model_id = "eu.amazon.nova-micro-v1:0"`. The guard call is
**unconditional** — `generation_service.py`'s `generate()` always calls
`_guard_prompt()` before generation; there is no condition that skips it.

### 5.2 Results — 100 / 1,000 / 10,000 users × low / baseline / heavy

| Profile | 100 users | 1,000 users | 10,000 users |
|---|---|---|---|
| **Low** | $0.05/mo | $0.49/mo | $4.90/mo |
| **Baseline** | $0.50/mo | $5.03/mo | $50.34/mo |
| **Heavy** | $5.40/mo | $53.97/mo | $539.71/mo |

Bedrock cost scales almost perfectly linearly with users × activity — no
surprises, no cliff. At every point in this grid, Bedrock is a minority of
total prod spend except at heavy+10,000 (§9).

---

## 6. Storage cost model

### 6.1 Database schema (confirmed via Liquibase/SQLAlchemy code research)

The entire database is **6 tables**. Only one matters for storage growth:

| Table | Growth driver | Storage behavior |
|---|---|---|
| `notebooks.notebooks` | 1 row/notebook, **single JSONB `cells` blob** holding the whole notebook (code + text cells) | **The only storage driver that scales with content.** No purge job found — soft-delete only (`deleted_at`), so history accumulates forever. |
| `notebooks.notebook_ai_context` | 1 row/notebook | Hard-capped at ≤8 KB context + small summary — **does not grow with AI request volume**, only with notebook count. Repeated `/llm/generate` calls mutate this row, they don't add rows. |
| `users.users`, `users.sessions`, `users.otps`, `users.refresh_tokens` | Auth activity | All bounded by cleanup jobs (OTP: 24h grace; sessions/refresh tokens: 90-day retention) — negligible absolute size at any scale in this report. |

There is **no AI-generation-history table and no execution-history table**
anywhere in the schema — confirmed via repo-wide search. AI request volume
does not itself add database rows.

### 6.2 Formula

```text
notebooks_per_user (steady state) = notebooks_created_per_user_per_month × 12   (months accumulated, no purge)
raw_notebook_storage_gb            = users × notebooks_per_user × avg_notebook_size_kb / 1024 / 1024
db_storage_with_overhead           = raw_notebook_storage_gb × 2.0    (JSONB/TOAST + indexes + WAL overhead)
monthly_storage_cost               = db_storage_with_overhead × $0.132/GB-month (gp3, eu-north-1 estimate)
```

### 6.3 Results

| Profile | 100 users | 1,000 users | 10,000 users |
|---|---|---|---|
| **Low** (raw→w/overhead) | 0.029→0.057 GB / **$0.008/mo** | 0.29→0.57 GB / **$0.076/mo** | 2.9→5.7 GB / **$0.757/mo** |
| **Baseline** | 0.11→0.23 GB / **$0.030/mo** | 1.1→2.3 GB / **$0.303/mo** | 11.4→22.9 GB / **$3.03/mo** |
| **Heavy** | 1.0→2.1 GB / **$0.272/mo** | 10.3→20.6 GB / **$2.72/mo** | **103→206 GB / $27.24/mo** ⚠️ |

⚠️ **The heavy + 10,000-user cell exceeds the Terraform-configured RDS
`max_allocated_storage = 100 GiB` autoscale ceiling** (raw data alone is
already ~103 GB before the 2× overhead multiplier). This is the one
concrete scaling wall this report finds in the current infrastructure —
see §10.

---

## 7. Traffic and CloudFront cost model, and Bedrock sensitivity analysis

### 7.1 Traffic formula and results

```text
monthly_sessions   = users × active_days × sessions_per_active_day
cloudfront_gb       = users × (1 full bundle re-fetch/mo × bundle_size_mb/1024)
                      + monthly_sessions × (5 KB shell re-fetch / 1024 / 1024)
sync_traffic_gb     = users × active_days × avg_notebook_size_kb / 1024 / 1024     (background autosync proxy — see note below)
ai_traffic_gb       = monthly_ai_requests × ~12 KB round trip / 1024 / 1024
```

**Cell execution generates zero traffic to AWS** (§3 — client-side WASM).
Notebook sync is **automatic background autosync, not a manual button** —
per `AGENTS.md` §1 and `docs/System_Architecture.md`, edits autosave
locally first and then push to the server in the background; `ui`'s
`docs/architecture/remote-sync.md` confirms the mechanism: a debounce
(`REMOTE_DEBOUNCE_MS = 1500`) coalesces a burst of local saves into one
push, and **every push sends the whole document**, not a delta. There is
no telemetry in the codebase on how many debounce cycles a real editing
session produces, so the "once per active day" multiplier here is a
**deliberately conservative placeholder for an unmeasured quantity**, not
a measured sync rate — actual background-push volume, driven by edit
frequency and debounce/coalescing behavior, is plausibly higher than this
model assumes. Flagged as a placeholder pending real telemetry, same
status as the retry-rate and UI-bundle-size assumptions (§3, §10).

| Profile | 100 users | 1,000 users | 10,000 users |
|---|---|---|---|
| Low (CloudFront $/mo) | $0.020 | $0.202 | $2.016 |
| Baseline (CloudFront $/mo) | $0.053 | $0.533 | $5.326 |
| Heavy (CloudFront $/mo) | $0.159 | $1.594 | $15.937 |

ALB data-processed and LCU costs stay under 1 LCU-equivalent at every
point in this grid (sync + AI traffic tops out around 51 GB/month at
heavy+10,000 users, well under the 1 GB/hour-per-LCU threshold) — folded
into the §4.1 ALB base charge, not separately broken out.

**This entire section is placeholder-sensitive to bundle size** (§3) —
replace `bundle_size_mb` with Engineer #3's measured figure; CloudFront
cost scales linearly with it.

### 7.2 Bedrock sensitivity analysis — worst case, single abusive/buggy user

This is the most consequential number in this report. There is **no
per-day or per-month cap** on AI usage anywhere in the code
(`docs/ai-architecture.md` itself flags this as an open, undecided
question) — only a 20 req/min/user limiter
(`api/app/modules/llm/services/rate_limiter.py`), and it is an in-process
`InMemoryRateLimiter`, **not shared across the 2–6 autoscaled API
replicas**. Modeling one user who sustains the per-minute cap
continuously for a full month, with every request hitting max retries (3
generator calls) and every call hitting its token ceiling:

```text
requests/month  = 20/min × 60 × 24 × 30                = 864,000
generator_calls = requests × 3 (max retries)             = 2,592,000
generator_input  = calls × 4,000 tok (prompt+context ceiling)
generator_output = calls × 2,048 tok (LLM_MAX_TOKENS ceiling)
guard_input      = requests × 2,850 tok (guard prompt ceiling)
guard_output     = requests × 256 tok (guard max_tokens ceiling)
```

| | Cost |
|---|---|
| Generator (Nova Lite) cost | **$1,896.10/mo** |
| Guard (Nova Micro) cost | **$117.15/mo** |
| **Total, one abusive/buggy user** | **$2,013.25/mo** |
| **If spread across all 6 autoscaled replicas** (per-process limiter ⇒ effective 6× rate) | **up to $12,079.50/mo** |

This is a theoretical ceiling (every request maxing every limit
simultaneously), not a realistic legitimate-usage figure — but it is the
actual exposure with the current code, and it dwarfs every aggregate
legitimate-usage scenario in §5.2. The $12,079.50/mo replica-spread figure
assumes ALB target-group stickiness is disabled, which matches the current
config — no `terraform/modules/backend` resource sets a `stickiness` block,
so AWS's default (disabled) applies, and a single user's requests can land
on any of the 2–6 replicas. Enabling stickiness would pin one client to one
replica and cap the realistic per-user ceiling back down to the
single-replica figure, ~$2,013.25/mo. See §9 (optimization
recommendations).

---

## 8. Fixed vs. variable cost summary

| Cost driver | Fixed or variable | Scales with |
|---|---|---|
| ECS Fargate API (floor) | Fixed (2-task floor) + variable (autoscale to 6) | CPU load, indirectly user count |
| ALB | Fixed (hourly) + negligible variable (LCU) | Request volume (negligible at modeled scale) |
| RDS instance (Multi-AZ) | **Fixed** | Not at all — same cost at 100 or 10,000 users |
| RDS storage | Variable | Notebook count × size, **unbounded growth (no purge)** |
| NAT Gateway | Fixed (hourly) + negligible variable | Egress data volume (negligible at modeled scale) |
| Bedrock VPC endpoint | **Fixed** | Not at all |
| Bedrock tokens | Variable | AI requests × prompt/completion size × retries |
| CloudWatch | Variable, currently trivial | Request/log volume |
| S3 / CloudFront | Variable, currently trivial | Sessions × bundle size, **unbounded version growth (no S3 lifecycle)** |
| ECR | Variable, **unbounded** | Deploy frequency, not users |
| Preview shared layer | **100% fixed** | Not at all — same cost regardless of dev activity |
| Per-PR preview slice | Variable | Open PR count, not users |

**Takeaway:** of the ~$119–161/mo prod floor, essentially none of it is
sensitive to user count except the ECS autoscale band ($20.72→$62.17) and
RDS/CloudFront/CloudWatch's usage-driven components, which stay under
$50/mo combined even at 10,000 heavy users (§6, §7). The dominant fixed
costs (RDS Multi-AZ instance, NAT, ALB, Bedrock VPC endpoint) are **the
same dollar amount whether the product has 100 users or 10,000.**

---

## 9. Total monthly cost by scenario

Production total = Bedrock + prod fixed floor ($119.37, using the 2-task
autoscale floor as the steady-state assumption) + RDS storage + CloudFront
traffic + CloudWatch logs + monitoring/analytics (≈$2.20/mo, §4.4) + ECR
placeholder ($8/mo). **Preview's ~$119.44/mo fixed floor and per-PR slice
costs are environment-level, not part of this per-scenario total** —
see §4.2/§4.3.

| Profile | 100 users | 1,000 users | 10,000 users |
|---|---|---|---|
| **Low** | **$129.64/mo** | **$130.35/mo** | **$137.39/mo** |
| **Baseline** | **$130.16/mo** | **$135.50/mo** | **$188.92/mo** |
| **Heavy** | **$135.42/mo** | **$188.12/mo** | **$715.11/mo** |

Add **~$119.44/mo** flat for the always-on preview/dev layer in every
cell above, plus **~$0.345/day per concurrently open PR**, to get total
AWS spend across all environments. At baseline usage and 1,000 users, for
example: **$135.50 (prod) + $119.44 (preview) ≈ $254.94/mo total**, before
any open-PR slices.

**Revenue-coverage framing.** At baseline + 1,000 users, ~$255/mo total
AWS spend ÷ 1,000 users ≈ **$0.25/user/month** to break even on
infrastructure alone (excluding engineering cost, support, etc.) — even a
small fraction of users on a paid tier, or a modest per-user margin on a
freemium model, comfortably covers this. The picture changes only at the
heavy+10,000-user combination, where ~$540/mo of that is Bedrock spend
driven by AI-heavy usage — a segment that, if monetized (e.g., AI
generation as a paid feature), would directly fund its own marginal cost.
This is framing for a stakeholder discussion, not a cost claim — it
excludes engineering time, support, and any non-AWS line item, none of
which this report models.

---

## 10. Risks and missing data

- **No per-day/month AI usage cap** (§7.2) — the single largest cost
  exposure in this report. `docs/ai-architecture.md` already flags this as
  an open question; this report quantifies it at up to **$12,080/mo from
  one user** under the current per-process rate limiter.
- **RDS storage ceiling (100 GiB) can be exceeded** at heavy usage + 10,000
  users due to unpurged notebook history (§6.3) — needs either a higher
  `max_allocated_storage`, a notebook archival/purge policy, or both.
- **No ECR lifecycle policy** — image storage cost is real but untracked by
  any code in this repo; the $8/mo figure used here is a placeholder, not a
  measurement. Recommend an `aws ecr describe-images` audit before trusting
  any ECR number in this report, and a dedicated follow-up issue to add a
  lifecycle policy (§4.5) — this single fix closes both the cost-tracking
  gap here and the unbounded-growth risk.
- **No S3 lifecycle rule** on the versioned prod UI bucket — old object
  versions accrue indefinitely. Currently negligible in dollars (§4.6) but
  unbounded in principle.
- **Monitoring/analytics CloudWatch additions (§1.6, §4.4) are new since
  this report's original base** and are now priced (≈$2.20/mo, folded into
  §9) — re-check this line if more alarms/dashboards/metric filters are
  added later, since dashboards #4+ cost $3/mo each past the 3-free tier.
  Both Terraform-defined dashboards (`jsnotes-t2`, `jsnotes-t2-analytics`
  from #169) are now live after the roll-forward fix (`1ad66a5`) merged
  and applied (§1.6, §4.4); this never changed the dollar figure either
  way.
- **On-demand bastion EC2 (PR #158, `terraform/modules/bastion`) is not
  cost-modeled** — `create_bastion` defaults to `false` (no resource
  created, $0), so this is a deliberate omission, not an oversight. If
  enabled for a DB session, it's a `t3.nano` (~$0.006/hr **[estimate]**) —
  trivial for occasional use, but remember to disable it again afterward
  (see `AGENTS.md` §6).
- **Most AWS unit prices in this report are estimates, not confirmed
  `eu-north-1` figures** — flagged individually in §11.1. WebFetch against
  AWS's pricing pages in this session returned flat marketing pages, not
  the region-filtered pricing tables (those load via client-side
  JavaScript) — confirmed prices came from targeted web search results and
  this repo's own cost-estimate comments in `docs/aws-cloud-migration.md`,
  not a live AWS Pricing Calculator session. **Re-run this through
  calculator.aws for `eu-north-1` before using these numbers for a real
  budget decision.**
- **UI bundle size is a placeholder** (§3, §7.1) pending Engineer #3's
  measurement — CloudFront traffic cost scales linearly with it but is
  small in every scenario studied (under $16/mo even at heavy+10,000
  users), so this is a low-risk placeholder, not a load-bearing one.
- **No usage telemetry exists yet** for retry rate, actual guard token
  consumption (not logged anywhere — only the generator's final usage is
  surfaced, per `generation_service.py`), real session/notebook patterns,
  or background-autosync push frequency (§7.1's "once per active day"
  sync-traffic multiplier is a placeholder, not a measured debounce-cycle
  rate). All usage-profile numbers in §3 are assumptions for planning
  purposes, not measurements — revisit once Cost Explorer / CloudWatch has
  real production data to compare against.

---

## 11. Appendix

### 11.1 Pricing inputs used (region: `eu-north-1` unless noted)

| Item | Value | Status |
|---|---|---|
| Fargate vCPU-hour | $0.04655 | **[estimate]** us-east-1 $0.04048 × 1.15 eu-north-1 uplift |
| Fargate GB-hour | $0.00511 | **[estimate]** us-east-1 $0.004445 × 1.15 |
| ALB hourly | $0.0287 | **[confirmed]** EU rate €0.0266/hr × 1.08 USD/EUR |
| ALB LCU-hour | $0.0085 | **[confirmed]** EU rate €0.0079/LCU-hr × 1.08 |
| RDS `db.t3.micro` Single-AZ | $0.0207/hr | **[estimate]** ~$0.018/hr common baseline × 1.15 |
| RDS `db.t3.micro` Multi-AZ | $0.0414/hr | **[estimate]** 2× Single-AZ |
| RDS gp3 storage | $0.132/GB-mo | **[estimate]** $0.115 × 1.15 |
| NAT Gateway | $0.045/hr + $0.045/GB | **[confirmed]** uniform across regions incl. eu-north-1 |
| VPC Interface Endpoint | $0.01/hr/AZ + $0.01/GB | **[confirmed]** matches this repo's own documented $15/mo/endpoint/2AZ figure |
| CloudFront data transfer (Europe, first 10 TB) | $0.085/GB | **[confirmed]** |
| CloudFront HTTPS requests | $0.0100/10k | **[estimate]**, standard rate, not EU-specific-verified |
| S3 Standard storage | $0.0253/GB-mo | **[estimate]** $0.023 × 1.10 |
| ECR storage | $0.10/GB-mo | **[confirmed]** example rate (region not explicitly broken out, but ECR storage pricing is largely uniform) |
| CloudWatch Logs ingestion | $0.50/GB | **[confirmed]** us-east-1 baseline; EU may run slightly higher |
| CloudWatch Logs storage | $0.03/GB-mo | **[confirmed]** baseline |
| CloudWatch Alarms | $0.10/alarm-month | **[confirmed]** |
| CloudWatch Dashboards (4th and beyond; first 3/account free) | $3/dashboard-month | **[confirmed]** |
| CloudWatch custom metrics (incl. log-metric-filter outputs) | $0.30/metric-month | **[confirmed]** |
| Route 53 health check (basic, non-AWS endpoint) | ≈$0.50/month | **[estimate]** |
| EC2 `t3.nano` on-demand | $0.0060/hr | **[estimate]** us-east-1 $0.0052/hr × 1.15 eu-north-1 uplift |
| Nova Lite (generator) | $0.06/1M input, $0.24/1M output | **[confirmed]** via web search; cross-region "eu." inference profile pricing not separately verified as a premium tier |
| Nova Micro (guard) | $0.035/1M input, $0.14/1M output | **[confirmed]** via web search |

### 11.2 Worked formulas

See §5.1 (Bedrock), §6.2 (storage), §7.1 (traffic) for the exact formulas
used; all scenario tables in this document were computed from these
formulas, not estimated by hand — the calculation script is reproducible
from the formulas as written.

### 11.3 Calculator and pricing links (re-verify before final submission)

- AWS Pricing Calculator: <https://calculator.aws/>
- Amazon Bedrock pricing: <https://aws.amazon.com/bedrock/pricing/>
- AWS Fargate pricing: <https://aws.amazon.com/fargate/pricing/>
- Amazon RDS pricing: <https://aws.amazon.com/rds/pricing/>
- Amazon VPC pricing (NAT + PrivateLink): <https://aws.amazon.com/vpc/pricing/>
- CloudFront pricing: <https://aws.amazon.com/cloudfront/pricing/>
- Elastic Load Balancing pricing: <https://aws.amazon.com/elasticloadbalancing/pricing/>
- Amazon S3 pricing: <https://aws.amazon.com/s3/pricing/>
- Amazon ECR pricing: <https://aws.amazon.com/ecr/pricing/>
- Amazon CloudWatch pricing: <https://aws.amazon.com/cloudwatch/pricing/>
- AWS Cost Explorer: <https://docs.aws.amazon.com/cost-management/latest/userguide/ce-what-is.html>
- AWS Budgets: <https://docs.aws.amazon.com/cost-management/latest/userguide/budgets-managing-costs.html>

### 11.4 Related project docs

- [`docs/aws-cloud-migration.md`](aws-cloud-migration.md) — current cloud
  architecture; source of the Bedrock VPC endpoint cost figure this report
  cross-checked against.
- [`docs/preview-v2.md`](preview-v2.md) — preview layer design, including
  the NAT-vs-endpoints decision (D) referenced in §4.7.
- [`docs/bedrock-smoke-test.md`](bedrock-smoke-test.md) — Bedrock
  connectivity runbook.
- [`docs/ai-architecture.md`](ai-architecture.md) — generation pipeline,
  retry/repair logic, and the open per-user-cost-ceiling question (§7.2,
  §10).
- `aws-cloud-migration.md` § Monitoring (added by
  `larchanka-training/dmc-1-t2-notebook-mono#153`) — the CloudWatch
  alarms/SNS/dashboard detail behind §4.4's cost figures.
