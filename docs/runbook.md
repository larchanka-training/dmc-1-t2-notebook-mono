# JS Notebook — Disaster Recovery Runbook

> **Status:** draft, Sprint #3 (2026-06-16). Sources of truth:
> AWS Console / live `aws describe-*` (current state) and `terraform/`
> (intended state). Commands in this document use canonical resource
> names from `terraform/`; variable values (e.g. the currently active
> task-definition revision) are looked up via `describe-*` at incident
> time, not written into the document.
>
> Related documents: `docs/aws-cloud-migration.md`,
> `docs/preview-v2.md`, `docs/bedrock-smoke-test.md`, `docs/ci-cd.md`.

## Prerequisites

Before using this runbook make sure you have:

1. **AWS credentials** for account `867633231218`, region `eu-north-1`:
   - for diagnostics (`describe-*`, `list-*`) — an IAM user with
     `arn:aws:iam::aws:policy/ReadOnlyAccess`;
   - for recovery (rollback, restore, secret rotation) — `deploy-user`
     level rights (ECS/RDS/S3/VPC/CloudFront/CloudWatchLogs/IAM/
     SecretsManager + `SecretsManagerReadWrite`);
   - as of 2026-06-16 the account owner is the course instructor.
2. **AWS CLI v2** (`aws --version` ≥ 2.x).
3. **Session Manager plugin** for `aws ecs execute-command`
   (`brew install --cask session-manager-plugin` on macOS).
4. **GitHub CLI** (`gh`) with the right to run `workflow_dispatch` in
   `larchanka-training/dmc-1-t2-notebook-mono` (for rollback via
   `deploy-cloud.yml`).
5. A local clone of the monorepo + submodules (`api/`, `ui/`).

If something is missing — that is not an excuse to skip the runbook,
it is the first line of the postmortem: "the incident was delayed by N
minutes because the on-call engineer lacked access."

---

## 1. Scope, contacts, severity

### 1.1. Scope

This runbook covers production incidents for JS Notebook (T2). In scope:

- prod ECS Fargate API service `jsnotes-t2-api`;
- prod RDS PostgreSQL `jsnotes-t2-db`;
- prod CloudFront distribution (UI + API via `/api/v1/*`);
- prod S3 bucket `jsnotes-t2-frontend`;
- AWS Bedrock (Nova Lite/Micro) integration for the Cloud agent;
- Resend as the provider for OTP email;
- AWS Secrets Manager containers `jsnotes-t2-*`;
- DNS / domain ownership (`jsnb.org`) on the Cloudflare side.

Out of scope:

- preview-per-PR slices (see `docs/preview-v2.md`);
- local development (`docker-compose.yaml`);
- multi-region disaster recovery (educational scope — manual redeploy
  only);
- developer-side incidents (broken submodule pointer, etc.).

#### Project status and funding context

JS Notebook is an educational project that **continues to be
developed** post-Sprint #3 (owner: Marat G.). This means the runbook
is a real operational document, not a release artefact, and the
follow-ups from §3.2, §5.7, §6.8, §9.8, §10.11, §11.6 are a genuine
roadmap, not "formality".

**Resource ownership structure:**

| Resource                   | Owner                    | After the course                 |
|----------------------------|--------------------------|----------------------------------|
| AWS account `867633231218` **(shared with T1 team!)** | Course instructor (account admin) | See §11 Scenario G |
| Domain `jsnb.org` (Cloudflare) | Marat G.              | Stays (available under any outcome) |
| Cloudflare Email Routing for `*@jsnb.org` | Marat G. | Free, stays; forwards to a personal gmail |
| Resend account              | Marat G. (personal)     | Stays                            |
| GitHub repos (mono/api/ui)  | `larchanka-training` org | Available read-only              |
| Bedrock model access        | Tied to the AWS account | Leaves with the AWS account      |

> ⚠ **Shared course account.** AWS account `867633231218` is used by
> both T2 (us) and T1 (the other course team). Source:
> `docs/aws-cloud-migration.md`, `docs/ai-architecture.md` ("shared
> course account"), `docs/preview-v2.md` (T1 ui/api repos). This
> affects:
>
> - **Scenario D (secret leak):** a `deploy-user` key leak compromises
>   access to **both** teams' resources — a notify chain to T1 + AWS
>   admin is mandatory (§8.0 cascade);
> - **AWS Budget / quotas:** a T1 budget overrun can trigger suspend
>   of T2 resources (and vice versa);
> - **IAM changes** via `deploy-user` affect both teams;
> - **Region capacity / VPC limits:** we already had `VpcLimitExceeded`
>   incidents because of the shared `5 VPCs per region` limit (see
>   `docs/aws-cloud-migration.md`).

**Three possible outcomes for AWS after the course ends** (detailed in
Scenario G, §11):

- **G.continue** — the instructor keeps paying for AWS;
- **G.handover** — AWS billing and ownership transfer (potentially to
  Marat G.); constraint: AWS account creation/billing for residents of
  RF is restricted by sanctions, so registering a new AWS Organization
  would need to be verified (alt: AWS reseller via a third country, an
  AWS Free Tier account on an EU / non-RF legal entity);
- **G.shutdown** — AWS is shut down; the domain and Resend stay with
  Marat; repositories and local code are intact; a future restart on
  fresh infra is possible.

This structure is **critical for DevOps**: under Scenario D (secret
leak) and Scenario E (Bedrock budget) we need to know each resource's
owner so we know whom to ask for rotation.

### 1.2. Contacts

| Role                          | Who (as of 2026-06-17)          | When to call                    |
|-------------------------------|---------------------------------|---------------------------------|
| AWS account admin (shared T1/T2) | Course instructor            | Sev-1, AWS key rotation, billing, IAM, quota requests, account-level kill |
| **T1 team contact**           | **TBD (handle needed)**         | **Any action affecting shared resources: secret leak, IAM, billing spike, quota** |
| Domain owner (`jsnb.org`, Cloudflare) | Marat G.                | DNS incidents, ACM cert renewal, alias switching |
| Resend account owner          | Marat G.                        | OTP email outage, Resend key, Verified Sender |
| Primary on-call (DevOps T2)   | Marat G.                        | All Sev-1..3 incidents          |
| Backup on-call                | TBD (fill in after Sprint #3)   | If primary is unavailable       |
| Tech Lead T2                  | TBD until end of course         | Sev-1, architectural decisions  |
| QA                             | TBD until end of course         | Post-recovery regression smoke  |

**Escalation chain for shared-account incidents:**

```
T2 on-call (Marat) → Course instructor (AWS admin) → T1 team contact
                  ↑
            mandatory for Scenario D
            (any key leak) and Scenario E
            (Bedrock budget overrun)
```

**TBD fields** — a normal state for an educational project at this
stage; they will be filled in via a follow-up PR. **T1 contact is the
top priority to fill in before publishing the runbook** (without it,
the §8 deploy-key cascade has no complete recovery chain).

### 1.3. Severity model

| Severity | Signs                                                                | Reaction                                |
|----------|----------------------------------------------------------------------|-----------------------------------------|
| Sev-1    | Production unavailable; data loss; auth bypass; key leak; XSS that executed for a user | Immediate mobilization; rollback / freeze; communication to everyone |
| Sev-2    | Major feature broken (sync, LLM cloud fully); serious latency degradation; rate-limit broken | Rollback within an hour; focused work during business hours |
| Sev-3    | Workaround exists; limited UX issue; one feature degrades            | Plan within the sprint                  |
| Sev-4    | Cosmetic, copy                                                       | Backlog                                 |

The severity model is aligned with QA release certification
(`release-report.md`).

---

## 2. Environments and URLs

### 2.1. Production

| Parameter                       | Value                                          |
|---------------------------------|------------------------------------------------|
| Primary URL                     | `https://jsnb.org`, `https://www.jsnb.org`     |
| CloudFront fallback URL         | `https://d3mdkzwy5yknm5.cloudfront.net`        |
| CloudFront distribution         | `E29EW3R1X0PB5W` (confirm with `list-distributions`) |
| DNS                             | Cloudflare → ACM cert in `us-east-1` → CloudFront aliases |
| AWS region                      | `eu-north-1`                                   |
| AWS account                     | `867633231218`                                 |
| ECS cluster                     | `jsnotes-t2`                                   |
| ECS service                     | `jsnotes-t2-api`                               |
| Task family (API)               | `jsnotes-t2-api`                               |
| Task family (migrations)        | `jsnotes-t2-migrations`                        |
| ALB                             | `jsnotes-t2-alb` (HTTP only; CloudFront terminates TLS) |
| RDS                             | `jsnotes-t2-db` (postgres 16, db.t3.micro)     |
| S3 (UI)                         | `jsnotes-t2-frontend`                          |
| Log group (API)                 | `/ecs/jsnotes-t2-api` (14 day retention)       |
| Log group (migrations)          | `/ecs/jsnotes-t2-migrations`                   |
| Bedrock generator               | `eu.amazon.nova-lite-v1:0`                     |
| Bedrock guard                   | `eu.amazon.nova-micro-v1:0`                    |

### 2.2. Preview (shared layer, not covered by this runbook)

| Parameter      | Value                                     |
|----------------|-------------------------------------------|
| URL            | `https://d2e2ymc27fdfn5.cloudfront.net`   |
| Shared DB      | `preview_main`                            |
| Per-PR API     | `preview-pr-<N>` Fargate service          |
| UI             | under `/pr-<N>/` on the shared CloudFront |

If preview breaks — this is not a Sev-1 for users; fix through the
normal PR flow.

### 2.3. Smoke check (single source of truth)

After any recovery operation this block is the final check:

```bash
# 1. CloudFront → S3 UI (200, content from index.html)
curl -fsS -o /dev/null -w "UI: %{http_code} %{size_download}b %{time_total}s\n" \
  https://jsnb.org/

# 2. API health via CloudFront
curl -fsS https://jsnb.org/api/v1/health
# Expectation: 200 OK + JSON { "status": "ok", ... }

# 3. OTP request (to a test email)
curl -fsS -X POST https://jsnb.org/api/v1/auth/otp/request \
  -H 'Content-Type: application/json' \
  -d '{"email":"qa+runbook@jsnb.org"}'
# Expectation: 202 Accepted (or 429 if rate-limited — that's OK too)

# 4. ALB direct (if CloudFront → 5xx, figure out whether it's ALB or CF)
ALB_DNS=$(aws elbv2 describe-load-balancers --names jsnotes-t2-alb \
  --query 'LoadBalancers[0].DNSName' --output text)
curl -fsS "http://${ALB_DNS}/api/v1/health"
```

If all 4 pass — the recovery is considered successful.

---

## 3. Section 0 — Detection and Paging

### 3.1. Current state of detection

**Honestly: detection in the project right now is reactive — "we
learn from a user or a colleague".** There are no CloudWatch alarms
(other than the built-in ECS circuit breaker), no SNS topics, no AWS
Budgets, no uptime monitor in IaC. This is **the project's biggest
operational gap** and is recorded in
`_private/notes/sprint3/infra-baseline.md` §8.

This means every scenario in §5–§11 has a **time-to-detect gap** that
the runbook itself cannot close. The on-call engineer has to remember
the daily mini-smoke (§3.3). Per-scenario time-to-detect (TTD)
estimates:

| Scenario | Detection channel | TTD (typical) |
|----------|-------------------|---------------|
| A — DB loss | API 5xx → user complaint / manual describe-services | 5–60 minutes |
| B — API down | GH Actions `deploy-cloud.yml` red (sync with deploy); user complaint (async) | 0–30 minutes |
| C — Region outage | AWS Health page / user report | 5–30 minutes |
| D — Secret leak | GitHub secret-scan alert / abuse pattern / external reporter | minutes — weeks (the worst case) |
| E — Bedrock budget | **No automatic signal today** (Cost Explorer lag ≥ 24h) → see §9.1 for the workaround | up to 24+ hours |
| F — Resend outage | OTP request fail / Resend status page | minutes — hours |
| G — Sunset | Planned event (known date) | N/A |

Known signal sources:

| Source                                          | What it shows                              | Detection latency         |
|-------------------------------------------------|--------------------------------------------|---------------------------|
| User complaint                                  | UI/API unavailable                          | minutes — tens of minutes |
| GitHub Actions `deploy-cloud.yml` red           | Failed deploy / circuit-breaker rollback    | immediately after push    |
| GitHub Actions `infra-cloud.yml` red            | Failed Terraform apply / secret bootstrap   | immediately after merge   |
| Manual CloudWatch Logs review                   | Startup errors, secret-related errors       | only when looked at       |
| Manual `aws ecs describe-services`              | Service not stable, frequent rollback events| only when looked at       |
| AWS Health Dashboard                            | Regional AWS issues                         | minutes after AWS notice  |
| CloudWatch Console metrics graphs               | 5xx burst, RDS CPU, ALB UnHealthyHostCount  | only when looked at       |

### 3.2. Follow-up: operational observability (out of scope for this runbook)

Things to add but tracked as a **separate task** (DevOps month 1
roadmap, Tech Lead-owned):

- CloudWatch alarms: ECS service `RunningTaskCount < desiredCount`;
  ALB `HTTPCode_Target_5XX_Count` burst; RDS `CPUUtilization` > 80%;
  RDS `DatabaseConnections` near max; CloudFront `5xxErrorRate`.
- SNS topic with an on-call email subscription.
- AWS Budget for Bedrock + ECS Fargate (requires extending
  `deploy-user` rights — it currently lacks `budgets:*`).
- CloudWatch Logs Metric Filters for patterns:
  - `"validation error" "configuration"` → secret bootstrap fail;
  - `"NoCredentialsError"` → IAM role not attached;
  - `"AccessDeniedException"` → IAM policy regression.
- CloudWatch Dashboard managed by Terraform.

### 3.3. What to do right now while observability is absent

The on-call engineer must run a mini-smoke **once a business day**
(5 minutes):

```bash
# CloudFront alive
curl -fsS -o /dev/null -w "%{http_code}\n" https://jsnb.org/
curl -fsS -o /dev/null -w "%{http_code}\n" https://jsnb.org/api/v1/health

# ECS service stable
aws ecs describe-services --cluster jsnotes-t2 --services jsnotes-t2-api \
  --query 'services[0].{Desired:desiredCount,Running:runningCount,Pending:pendingCount,LastStatus:deployments[0].rolloutState}' \
  --output table

# RDS available
aws rds describe-db-instances --db-instance-identifier jsnotes-t2-db \
  --query 'DBInstances[0].{Status:DBInstanceStatus,FreeStorageGB:`null`}' \
  --output table

# Recent API errors (last 30 minutes)
aws logs start-query --log-group-name /ecs/jsnotes-t2-api \
  --start-time $(date -u -v -30M +%s) --end-time $(date -u +%s) \
  --query-string 'filter @message like /ERROR|Exception|Traceback/ | stats count() by bin(5m)'
# Save the queryId, then call get-query-results
```

This compensates for the missing alarms with regular "human polling".
It is not a replacement for observability, just a temporary workaround.

### 3.4. Communication channels

| Channel                       | When                                        |
|-------------------------------|---------------------------------------------|
| Team chat (T2)                | Opening an incident, status every 30 min    |
| GitHub Issue in `mono` repo   | Sev-1 / Sev-2: create an issue with label `incident` |
| `_private/summaries_memory/`  | Postmortem summary after resolved           |

---

## 4. General incident flow

One skeleton for all scenarios A–F. Each scenario specifies its "Stop"
and "Recover" steps; the rest is uniform.

```text
1. IDENTIFY  ─── figure out what exactly broke (symptoms, version,
                 which component).
2. SCOPE     ─── prod or preview? UI or API? data loss or downtime?
                 are all users affected or only some?
3. STOP      ─── stop the bleeding: rollback, kill switch, rotate
                 secret, freeze deploy pipeline.
4. RECOVER   ─── steps for the specific scenario (see §5–10).
5. VERIFY    ─── §2.3 smoke check + scenario-specific checks.
6. COMMUNICATE ─ status in team chat + GitHub Issue update.
7. POSTMORTEM ── template in §12; save to
                 `_private/summaries_memory/`.
```

### 4.1. Identify — common diagnostic commands

```bash
# Is this a regional AWS issue?
# https://health.aws.amazon.com/health/status

# CloudFront/UI layer
curl -fsS -o /dev/null -w "CloudFront UI: %{http_code} %{time_total}s\n" \
  https://jsnb.org/
curl -fsS -o /dev/null -w "CloudFront API: %{http_code} %{time_total}s\n" \
  https://jsnb.org/api/v1/health

# ALB layer (bypassing CloudFront)
ALB_DNS=$(aws elbv2 describe-load-balancers --names jsnotes-t2-alb \
  --query 'LoadBalancers[0].DNSName' --output text)
curl -fsS -o /dev/null -w "ALB API: %{http_code} %{time_total}s\n" \
  "http://${ALB_DNS}/api/v1/health"

# ECS service state
aws ecs describe-services --cluster jsnotes-t2 --services jsnotes-t2-api \
  --query 'services[0].{TD:taskDefinition,Desired:desiredCount,Running:runningCount,Pending:pendingCount,Events:events[0:5].[createdAt,message]}' \
  --output json

# RDS state
aws rds describe-db-instances --db-instance-identifier jsnotes-t2-db \
  --query 'DBInstances[0].{Status:DBInstanceStatus,Engine:Engine,Endpoint:Endpoint.Address,Storage:AllocatedStorage,MultiAZ:MultiAZ}' \
  --output table

# Last 50 lines of API logs
aws logs tail /ecs/jsnotes-t2-api --since 30m --follow=false | head -100
```

### 4.2. Scope — decision table

| What the §4.1 commands show                              | Most likely scenario |
|----------------------------------------------------------|-----------------------|
| `CloudFront 5xx` + `ALB 5xx` + ECS service unhealthy     | B (API down)          |
| `CloudFront 5xx` + ALB OK                                | CloudFront/CF Function issue (rare) |
| ALB UnHealthyHostCount = desired, API tasks `STOPPED`    | B1 or B2              |
| RDS `Status != available`                                 | A                     |
| OTP user complaints + Resend dashboard red                | F                     |
| Notice of an unexpectedly high bill / LLM request count   | E                     |
| Notice of a compromised secret / public key               | D                     |
| eu-north-1 region shown as degraded on AWS Health         | C                     |

### 4.3. Stop the bleeding — common actions

These actions are safe even without a complete diagnosis and do not
make things worse:

1. **Freeze the deploy pipeline:** in GitHub disable
   `deploy-cloud.yml` (Actions → workflow → Disable), so that a new
   merge to `main` does not stack a second problem on top of the first.
2. **Save evidence:** screenshots of the CloudFront/ECS/RDS console;
   a copy of `describe-services` + `events` to a file; tail of logs to
   a file. This is needed for the postmortem.
3. **Do not run `terraform apply`** during an incident — it will
   overwrite parts of the task definition and make rollback harder.
4. **Communicate:** a status post in team chat: "Sev-X, symptoms are
   such-and-such, working on it."

The scenario-specific "stop" steps are in §5–10.

### 4.4. Recover, Verify, Communicate, Postmortem

- Recover: see the specific scenario §5–10.
- Verify: §2.3 smoke + scenario-specific steps.
- Communicate: status every 30 minutes in team chat; final message
  "Resolved at HH:MM".
- Postmortem: template in §12; save to a file like
  `_private/summaries_memory/incident_<YYYY-MM-DD>_<short>.md`.

---

## 5. Scenario A — Database loss / corruption

**Severity:** Sev-1 (data loss or production down) / Sev-2 (deploy red
only, API not affected). TTD: 5–60 minutes (see §3.1).

### 5.0. Architectural particulars that drive RTO/RPO

- **RDS single-AZ** (`multi_az = false` in `terraform/modules/data`).
  Instant Multi-AZ failover is not possible — any instance failure
  requires **manual restore**, which sets the lower bound on RTO at
  30+ minutes.
- **No read replica.** No stand-by to promote — only PITR /
  restore-from-snapshot.
- **No cross-region snapshot copy.** During a regional outage backups
  may be unreachable (see §11.6 follow-up + §17 Appendix D).
- **Notebooks live in offline-first IndexedDB** on the client: users'
  **local** notebooks **are not lost** even if the DB is completely
  gone — only the server-synchronized copies. Sync is manual, so the
  user-side RPO is **usually better** than the DB-side RPO. **Browser
  execution (QuickJS) and in-browser AI (WebLLM) continue to work
  while the backend is fully down.** This **reduces the user impact**
  of Scenario A from a full outage to "cannot sign in + cannot sync".

### 5.1. What counts as database loss

5 classes of problems that fall into this scenario:

| Class | Symptom | Where to look | Sub-scenario |
|-------|---------|----------------|--------------|
| A1. Instance gone | `aws rds describe-db-instances` → `DBInstanceNotFound`; ECS `connection refused` | RDS Console, CloudTrail | A.recover.instance |
| A2. Instance unhealthy | RDS `Status != available` (failed, storage-full, incompatible-parameters) | RDS Console events | A.recover.instance |
| A3. Data corruption / accidental delete | `psql` shows missing/corrupt rows; user bug report | API logs, RDS console | A.recover.pitr |
| A4. Migration broken | ECS migration task `exit != 0`; deploy-cloud.yml red on migration step | `/ecs/jsnotes-t2-migrations` log group | A.recover.migration |
| A5. Wrong `DATABASE_URL` | API container crash on startup: `could not connect`, `password authentication failed` | `/ecs/jsnotes-t2-api` startup logs | A.recover.secret |

**Important:** A4 and A5 are **not** Sev-1 "data loss". They are
config/deploy problems, usually fixed by a rollback or a secret
update. Scenarios A3 (PITR) and A1/A2 (restore) are the most
"expensive" in RTO.

### 5.2. Identify

```bash
# 1. RDS instance state
aws rds describe-db-instances --db-instance-identifier jsnotes-t2-db \
  --query 'DBInstances[0].{Status:DBInstanceStatus,Endpoint:Endpoint.Address,Engine:Engine,LatestRestorableTime:LatestRestorableTime,BackupRetention:BackupRetentionPeriod,MultiAZ:MultiAZ,Storage:AllocatedStorage,DeletionProtection:DeletionProtection}' \
  --output table

# 2. Events for the last day
aws rds describe-events --source-identifier jsnotes-t2-db \
  --source-type db-instance --duration 1440 \
  --query 'Events[].[Date,Message]' --output table

# 3. API startup errors
aws logs tail /ecs/jsnotes-t2-api --since 30m --filter-pattern '?ERROR ?Exception ?Traceback ?"could not connect" ?"password authentication"' \
  | head -200

# 4. Last migration result
aws logs tail /ecs/jsnotes-t2-migrations --since 24h | tail -200

# 5. ECS deploy events (to distinguish A5 from B1)
aws ecs describe-services --cluster jsnotes-t2 --services jsnotes-t2-api \
  --query 'services[0].events[0:10].[createdAt,message]' --output table
```

### 5.3. Decision tree

```
RDS Status != available?
  └── yes  → A1/A2 (instance recovery, §5.4.1)
  └── no
      ├── ECS migration task red?
      │   └── A4 (migration recovery, §5.4.3)
      ├── API logs: "could not connect" / "password authentication"?
      │   └── A5 (secret recovery, §5.4.5)
      └── Bug report about data loss / wrong data in notebooks?
          └── A3 (PITR, §5.4.2)
```

> ❗ **After any restore** (A1/A2/A3) — §5.4.4 (Terraform drift loop)
> is **mandatory**. Without it, an auto-apply of `infra-cloud.yml` can
> destroy the restored instance.

### 5.4. Recover

#### 5.4.1. A1/A2 — Instance recovery

If the instance is gone (A1) or unhealthy and not recovering on its
own (A2):

```bash
# Step 1. Confirm there is a recent snapshot or PITR window
aws rds describe-db-snapshots --db-instance-identifier jsnotes-t2-db \
  --snapshot-type automated --query 'DBSnapshots[*].{Id:DBSnapshotIdentifier,Created:SnapshotCreateTime,Status:Status,Storage:AllocatedStorage}' \
  --output table

# Step 2. Restore from the latest automated backup up to a point BEFORE
# the incident (recommend -5 minutes from incident time)
TARGET_TIME="2026-06-17T10:25:00Z"  # 5 minutes before incident_time
RESTORED_ID="jsnotes-t2-db-restore-$(date +%Y%m%d%H%M)"

aws rds restore-db-instance-to-point-in-time \
  --source-db-instance-identifier jsnotes-t2-db \
  --target-db-instance-identifier "$RESTORED_ID" \
  --restore-time "$TARGET_TIME" \
  --db-subnet-group-name jsnotes-t2-db-subnet-group \
  --vpc-security-group-ids "$(aws ec2 describe-security-groups \
      --filters Name=group-name,Values=jsnotes-t2-rds-sg \
      --query 'SecurityGroups[0].GroupId' --output text)" \
  --no-multi-az \
  --no-publicly-accessible \
  --deletion-protection \
  --db-instance-class db.t3.micro \
  --storage-type gp3

# Step 3. Wait for the restored instance to become available (10–30 min)
aws rds wait db-instance-available --db-instance-identifier "$RESTORED_ID"

# Step 4. Get the endpoint of the new instance
RESTORED_ENDPOINT=$(aws rds describe-db-instances \
  --db-instance-identifier "$RESTORED_ID" \
  --query 'DBInstances[0].Endpoint.Address' --output text)
echo "Restored endpoint: $RESTORED_ENDPOINT"
```

Then there are **two options for replacing the endpoint** in
`DATABASE_URL`:

- **Option A (fast, not Terraform-managed):** update the secret
  manually, then reconcile via Terraform later as a separate task.
  Faster RTO, but introduces drift.
- **Option B (via rename):** delete the old instance and rename the
  restored one to `jsnotes-t2-db` (its endpoint becomes the same as
  before). Slower RTO (≥ 10 min for rename + DNS propagation), no
  drift.

**Decision under Sev-1:** go with Option A for a fast recovery; after
resolution open a PR to reconcile.

Option A — updating the secret:

```bash
# Get the current creds from the db-migration secret (it contains JSON
# with username/password)
CREDS=$(aws secretsmanager get-secret-value \
  --secret-id jsnotes-t2-db-migration --query SecretString --output text)
DB_USER=$(echo "$CREDS" | jq -r .username)
DB_PASS=$(echo "$CREDS" | jq -r .password)

# Compose the new DATABASE_URL (DB name is 'wiki' — see infra-baseline.md §5)
NEW_URL="postgresql://${DB_USER}:${DB_PASS}@${RESTORED_ENDPOINT}/wiki"

# Write the new value into the secret
aws secretsmanager put-secret-value \
  --secret-id jsnotes-t2-database-url \
  --secret-string "$NEW_URL"

# Also update the db_migration JSON (for future migrations)
NEW_MIG=$(echo "$CREDS" | jq --arg u "jdbc:postgresql://${RESTORED_ENDPOINT}/wiki" '.url=$u')
aws secretsmanager put-secret-value \
  --secret-id jsnotes-t2-db-migration \
  --secret-string "$NEW_MIG"

# Apply via ECS force-new-deployment (new tasks will pick up the new secret)
aws ecs update-service --cluster jsnotes-t2 --service jsnotes-t2-api \
  --force-new-deployment

# Wait for stabilization
aws ecs wait services-stable --cluster jsnotes-t2 --services jsnotes-t2-api
```

After recovery — Verify (§5.5).

#### 5.4.2. A3 — PITR for point-in-time data restore

When the instance is alive but the **data is corrupted** (for example,
a migration accidentally dropped a column with data, or an app bug
overwrote notebooks).

**Strategy:** restore a separate instance to a point BEFORE the
incident, extract the needed tables/rows, import into the live
instance. Do not touch the live instance directly.

```bash
# Step 1. Pick the exact time before the incident
TARGET_TIME="2026-06-17T10:25:00Z"  # 5 minutes before the known incident_time
RESTORED_ID="jsnotes-t2-db-pitr-$(date +%Y%m%d%H%M)"

# Step 2. Restore into a temporary instance
aws rds restore-db-instance-to-point-in-time \
  --source-db-instance-identifier jsnotes-t2-db \
  --target-db-instance-identifier "$RESTORED_ID" \
  --restore-time "$TARGET_TIME" \
  --db-subnet-group-name jsnotes-t2-db-subnet-group \
  --vpc-security-group-ids "$(aws ec2 describe-security-groups \
      --filters Name=group-name,Values=jsnotes-t2-rds-sg \
      --query 'SecurityGroups[0].GroupId' --output text)" \
  --no-multi-az --no-publicly-accessible \
  --db-instance-class db.t3.micro --storage-type gp3

aws rds wait db-instance-available --db-instance-identifier "$RESTORED_ID"

# Step 3. Get the endpoint
RESTORED_ENDPOINT=$(aws rds describe-db-instances \
  --db-instance-identifier "$RESTORED_ID" \
  --query 'DBInstances[0].Endpoint.Address' --output text)

# Step 4. From bastion / ECS Exec container, pg_dump only the needed tables
TASK_ARN=$(aws ecs list-tasks --cluster jsnotes-t2 --service-name jsnotes-t2-api \
  --desired-status RUNNING --query 'taskArns[0]' --output text)

aws ecs execute-command --cluster jsnotes-t2 --task "$TASK_ARN" \
  --container api --interactive --command "/bin/sh"

# Inside the container:
# pg_dump "postgresql://${DB_USER}:${DB_PASS}@${RESTORED_ENDPOINT}/wiki" \
#   --table=users.notebooks --data-only > /tmp/notebooks.sql
# psql "$DATABASE_URL" < /tmp/notebooks.sql  # against the LIVE instance, carefully!

# Step 5. Delete the temporary instance
aws rds delete-db-instance --db-instance-identifier "$RESTORED_ID" \
  --skip-final-snapshot
```

**Important:** before importing into the live instance, agree with the
Tech Lead — this is a change to user data. It is desirable to back up
live data before the import (a separate snapshot).

#### 5.4.3. A4 — Migration recovery

When `deploy-cloud.yml` fails on the migration step.

> ⚠ **Liquibase + PostgreSQL failure semantics.** Postgres
> **auto-commits DDL** — which means that even if a migration "failed"
> and `deploy-cloud.yml` shows red, **part of the DDL may have been
> applied before the failure**. Liquibase changeset rollback only
> works if you explicitly defined `<rollback>` blocks in the
> changeset (by default there aren't any!). The source of truth is the
> `databasechangelog` table.

```bash
# Step 1. Read why the migration failed
aws logs tail /ecs/jsnotes-t2-migrations --since 60m | tail -300

# Step 2. Check the Liquibase bookkeeping state (databasechangelog =
# source of truth; not the file system, not Git)
# Via psql from ECS Exec:
# SELECT id, author, filename, dateexecuted, exectype, orderexecuted
#   FROM databasechangelog ORDER BY orderexecuted DESC LIMIT 10;
# SELECT * FROM databasechangeloglock;

# Step 2b. Compare against the file system: for each change that is
# missing in databasechangelog but present in changelog-master.xml —
# it may be partially applied DDL without a journal entry (worst case).

# Step 3. If databasechangeloglock is stuck (LOCKED=true), release the lock:
# UPDATE databasechangeloglock SET LOCKED=FALSE, LOCKEDBY=NULL, LOCKGRANTED=NULL WHERE ID=1;

# Step 4. If partial DDL was applied without a databasechangelog entry
# (no `<rollback>` in the changeset) — the only clean recovery path is
# PITR (§5.4.2 A3) to a point before the migration ran.
# A forward fix via a new changeset is possible, but only if you know
# exactly which parts of the DDL were applied — that is often unclear
# from the logs.
#
# If `<rollback>` blocks exist in the changeset and Liquibase ran them
# (visible in the logs as "Rolling back changeset ..."), the DB is
# consistent — a forward fix via a new changeset is enough.
#
# NEVER edit an already-applied changeset — Liquibase checks the hash.

# Step 5. Re-deploy via workflow_dispatch with the correct image
gh workflow run deploy-cloud.yml \
  --ref main \
  -f api_image_tag=sha-<previous-good>
```

**Severity:** usually Sev-2 (deploy red, but the old API revision is
live). Sev-1 only if the migration damaged data (then switch to A3).

#### 5.4.4. ⚠ Mandatory sub-procedure: PITR → new endpoint → Terraform drift loop

After any restore (A1/A2/A3) **a drift between live and Terraform
state appears**. Without an explicit procedure, **the next
`terraform apply` (or auto-apply on push to `main`!) may try to "fix"
reality and recreate/roll back the DB** — that is a second incident
on top of the first.

**Mandatory order of operations** for any restore:

```bash
# Step 1. FREEZE infra-cloud.yml (auto-apply on push to main)
gh api -X PUT \
  /repos/larchanka-training/dmc-1-t2-notebook-mono/actions/workflows/infra-cloud.yml/disable

# Step 2. Run the restore from (§5.4.1, §5.4.2 or §5.4.5) —
#         obtain $RESTORED_ID
#         and the new $RESTORED_ENDPOINT.

# Step 3. Update derived secrets to the new endpoint
aws secretsmanager put-secret-value --secret-id jsnotes-t2-database-url \
  --secret-string "postgresql://${DB_USER}:${DB_PASS}@${RESTORED_ENDPOINT}/wiki"

aws secretsmanager put-secret-value --secret-id jsnotes-t2-db-migration \
  --secret-string "$(jq -n --arg u "$DB_USER" --arg p "$DB_PASS" \
    --arg url "jdbc:postgresql://${RESTORED_ENDPOINT}/wiki" \
    '{username:$u,password:$p,url:$url}')"

# Step 4. Roll the API onto the new secrets
aws ecs update-service --cluster jsnotes-t2 --service jsnotes-t2-api \
  --force-new-deployment
aws ecs wait services-stable --cluster jsnotes-t2 --services jsnotes-t2-api

# Step 5. Smoke (§2.3 + §12.1). The service should be alive on the same
#         secret identifiers but with the new endpoint behind them.
```

**Step 6 — reconcile Terraform state** (can be done within 24 hours
after recovery, **but before unfreezing infra-cloud**):

```bash
# Option A. Cleanest path — rename the restored instance back to
#           jsnotes-t2-db so Terraform sees no drift.
#           First turn off deletion_protection on the restored instance:
aws rds modify-db-instance --db-instance-identifier "$RESTORED_ID" \
  --no-deletion-protection --apply-immediately

# Then delete the old "broken" instance (if it still exists).
# Then rename the restored to jsnotes-t2-db via modify-db-instance.
# The endpoint will become the same again, secrets do not need updating.
# RTO: +20–30 minutes.

# Option B. If renaming is inconvenient — reconcile Terraform state
# (more expert, requires terraform CLI and state access):
cd terraform/cloud
terraform state rm 'module.data.aws_db_instance.this'
terraform import 'module.data.aws_db_instance.this' "$RESTORED_ID"
# Then fix the identifier in variables / hardcode so plan is a no-op.
```

**Step 7. ONLY AFTER Step 6** — unfreeze infra-cloud:

```bash
gh api -X PUT \
  /repos/larchanka-training/dmc-1-t2-notebook-mono/actions/workflows/infra-cloud.yml/enable

# Verify that the next plan on main is a no-op:
gh workflow run infra-cloud.yml --ref main
gh run watch
```

> ❗ **The most dangerous case:** with auto-apply enabled, someone
> merges even a docs-only PR into `main` → `infra-cloud.yml` runs
> `terraform apply` → Terraform sees "the DB is not the right one" →
> tries to destroy the restored instance and create a new one with
> empty data. **That is why freezing infra-cloud (Step 1) is not
> optional, but critical.**

#### 5.4.5. A5 — Secret recovery (wrong `DATABASE_URL`)

When the API does not start because of a wrong secret value:

```bash
# Step 1. Read the current value (only if really needed for
# diagnostics; usually a sanity check without reading is enough)
aws secretsmanager describe-secret --secret-id jsnotes-t2-database-url \
  --query '{LastChanged:LastChangedDate,VersionsToStages:VersionIdsToStages}' \
  --output json

# Step 2. If a previous version exists (AWSPREVIOUS), fast rollback:
aws secretsmanager update-secret-version-stage \
  --secret-id jsnotes-t2-database-url \
  --version-stage AWSCURRENT \
  --move-to-version-id "$(aws secretsmanager describe-secret \
      --secret-id jsnotes-t2-database-url \
      --query 'VersionIdsToStages | to_entries | [?contains(value, `AWSPREVIOUS`)] | [0].key' \
      --output text)" \
  --remove-from-version-id "$(aws secretsmanager describe-secret \
      --secret-id jsnotes-t2-database-url \
      --query 'VersionIdsToStages | to_entries | [?contains(value, `AWSCURRENT`)] | [0].key' \
      --output text)"

# Step 3. Force-new-deployment so ECS picks up the restored secret
aws ecs update-service --cluster jsnotes-t2 --service jsnotes-t2-api \
  --force-new-deployment

aws ecs wait services-stable --cluster jsnotes-t2 --services jsnotes-t2-api
```

### 5.5. Verify

1. Basic smoke (§2.3) — all 4 checks must pass.
2. DB-specific checks:

```bash
# Check the connection via the API health endpoint (it runs SELECT 1)
curl -fsS https://jsnb.org/api/v1/health

# Check that a real DB-bound endpoint works
# (OTP request runs INSERT into users.otps)
curl -fsS -X POST https://jsnb.org/api/v1/auth/otp/request \
  -H 'Content-Type: application/json' \
  -d '{"email":"qa+runbook@jsnb.org"}'

# If you have a test account with notebooks — check the list:
# (requires a valid JWT, see test fixtures)

# Via ECS Exec verify databasechangelog (if there was an A4):
aws ecs execute-command --cluster jsnotes-t2 \
  --task "$(aws ecs list-tasks --cluster jsnotes-t2 \
      --service-name jsnotes-t2-api --query 'taskArns[0]' --output text)" \
  --container api --interactive \
  --command "python -c 'from app.db import engine; import sqlalchemy as sa; \
    print(engine.execute(sa.text(\"SELECT count(*) FROM databasechangelog\")).scalar())'"
```

### 5.6. RTO / RPO

| Sub-scenario | RTO (target) | RPO (potential loss) |
|--------------|--------------|----------------------|
| A1/A2 instance recovery | 30–60 min (PITR + secret + roll) | ≤ 5 min back to `LatestRestorableTime` |
| A3 PITR data restore | 60–120 min (PITR + dump/import + agreement) | determined by the chosen `--restore-time` |
| A4 migration recovery | 30–90 min (fix changeset + redeploy) | 0 (no data loss) |
| A5 secret recovery | 10–15 min (revert version + roll) | 0 |

These numbers are a **best effort for the educational scope**
(db.t3.micro, single-AZ). For a real production team with Multi-AZ +
read replicas + a pre-rehearsed runbook the A1/A2 RTO would be 10–20
minutes.

### 5.7. Follow-ups (not part of this scenario)

- Restore drill on preview every 90 days (`preview_main` DB is not
  critical — a safe place to practise).
- Multi-AZ for RDS (~$15/month extra, but removes the A1/A2 risk).
- Cross-region snapshot copy (for the future Scenario C).
- Extend `deploy-user` with `events:*` for CloudWatch event rules on
  `RDS-EVENT-0009` (failover) and `RDS-EVENT-0006` (restart).

---

## 6. Scenario B — API down

**Severity:** Sev-1 (API unavailable) / Sev-2 (deploy red but the
service is rolled back to the old revision). TTD: 0–30 minutes.

The API is unavailable or unstable: `https://jsnb.org/api/v1/health`
returns 5xx, `502`, `504`, or CloudFront shows `503`. The UI usually
still loads (it lives on S3+CloudFront), but any auth/notebook
sync/LLM calls fail.

Three sub-scenarios:

- **B1.a — pipeline drift rollback:** `deploy-cloud.yml` historically
  copied env/secrets from the live task-def (not from the Terraform
  baseline), which led to silent drift accumulating over weeks. The
  fix has already been made (rendering from the Terraform baseline via
  `deploy-cloud.yml:97`), but old task-defs with drift may remain in
  the revision history.
- **B1.b — config regression (startup fail-fast):** a required secret
  has a missing/placeholder value under `APP_ENV=production` (see
  monorepo `larchanka-training/dmc-1-t2-notebook-mono#118` — pointer
  bump for the api OTP email delivery change — and the related
  production rollback on 14.06). The API does not start, the circuit
  breaker rolls back.
- **B2 — code crash:** the new image fails on startup or at runtime.

Their Identify is similar, the Recover differs radically.

### 6.1. Identify (common part for B1/B2)

```bash
# 1. Confirm that this is the API layer and not CloudFront/ALB
ALB_DNS=$(aws elbv2 describe-load-balancers --names jsnotes-t2-alb \
  --query 'LoadBalancers[0].DNSName' --output text)

curl -fsS -o /dev/null -w "CloudFront: %{http_code}\n" https://jsnb.org/api/v1/health
curl -fsS -o /dev/null -w "ALB direct: %{http_code}\n" "http://${ALB_DNS}/api/v1/health"

# If CloudFront 5xx and ALB 5xx → ALB or ECS, continue below.
# If CloudFront 5xx and ALB 200 → CloudFront/CF Function (rare case, §6.5).

# 2. ECS service state
aws ecs describe-services --cluster jsnotes-t2 --services jsnotes-t2-api \
  --query 'services[0].{TD:taskDefinition,Desired:desiredCount,Running:runningCount,Pending:pendingCount,RolloutState:deployments[0].rolloutState,RolloutStateReason:deployments[0].rolloutStateReason,Events:events[0:10].[createdAt,message]}' \
  --output json

# 3. Target group health (UnHealthy hosts reveal a crash or slow start)
TG_ARN=$(aws elbv2 describe-target-groups --names jsnotes-t2-api-tg \
  --query 'TargetGroups[0].TargetGroupArn' --output text)
aws elbv2 describe-target-health --target-group-arn "$TG_ARN" \
  --query 'TargetHealthDescriptions[].{Target:Target.Id,Port:Target.Port,State:TargetHealth.State,Reason:TargetHealth.Reason,Desc:TargetHealth.Description}' \
  --output table

# 4. Recent API logs (where the container crashed)
aws logs tail /ecs/jsnotes-t2-api --since 30m \
  --filter-pattern '?ERROR ?CRITICAL ?Exception ?Traceback ?"validation error" ?"startup"' \
  | head -300

# 5. Stopped tasks (if any — the stop reason is there)
STOPPED=$(aws ecs list-tasks --cluster jsnotes-t2 --service-name jsnotes-t2-api \
  --desired-status STOPPED --query 'taskArns' --output json)
echo "$STOPPED" | jq -r '.[]' | while read TASK; do
  aws ecs describe-tasks --cluster jsnotes-t2 --tasks "$TASK" \
    --query 'tasks[].{StoppedReason:stoppedReason,StopCode:stopCode,Containers:containers[].{Name:name,ExitCode:exitCode,Reason:reason}}' \
    --output json
done
```

### 6.2. Decision tree: B1 vs B2

| Symptom from §6.1                                                  | Scenario | Recovery   |
|---------------------------------------------------------------------|----------|------------|
| `RolloutStateReason: ECS deployment <id> failed... circuit breaker` + log `"validation error" / "missing required"` + secret name in the message | **B1.b** (startup fail-fast) | §6.3.3 |
| `RolloutStateReason: ECS deployment <id> failed... circuit breaker` + log about a **missing env var** that should have been there | **B1.a** (pipeline drift) | §6.3.4 |
| `RolloutStateReason: ECS deployment <id> failed... circuit breaker` + log `ImportError` / `Traceback` / `unhandled exception` | **B2**   | §6.4       |
| `stoppedReason: "Task failed ELB health checks"` + log without an obvious crash | B2 (slow start or health path mismatch) | §6.4 |
| `stoppedReason: "Essential container in task exited"` + `exitCode: 1` + log `RuntimeError`/`Traceback` | **B2** | §6.4    |
| `stoppedReason: "ResourceInitializationError: ... unable to pull secrets ... AccessDenied"` | **B1.a** (IAM/secret ARN drift) | §6.3.4 |
| `Running == Desired` but ALB direct returns 5xx                    | B2 (runtime exception, not a crash) | §6.4 |
| UI 200, ALB 5xx, ECS healthy                                       | CloudFront → ALB origin issue | §6.5 |

**Distinguishing B1.a vs B1.b — by log content:**

- **B1.b (missing/placeholder secret value):** `pydantic.ValidationError`
  / "secret must be set", i.e. the ARN is wired correctly but the
  **value** in Secrets Manager is missing or placeholder. Fix —
  `put-secret-value`.
- **B1.a (env/secret drift in the TD):** the container does not
  receive an ENV variable that should be there (according to the
  Terraform baseline it is present, according to the active TD it is
  not). Fix — re-create the TD from the Terraform baseline via
  `deploy-cloud.yml workflow_dispatch` or a manual
  `register-task-definition` from IaC.

A real B1.b example — `_private/summaries_memory/sprint2_follow-up/deploy_cloud_resend_secret_rollback_14_06_2026.md`:
after the monorepo PR
`larchanka-training/dmc-1-t2-notebook-mono#118` (a submodule pointer
bump to the api with production startup validation for OTP email
delivery), the API started requiring `RESEND_API_KEY` and
`EMAIL_FROM`, but Terraform/Secrets Manager did not have them. The
ECS circuit breaker rolled back the deployment.

### 6.3. B1 — Config regression recovery

A "bad" new task definition + ECS auto-rollback leaves the service on
the **previous live** revision. Most often the service is already
alive; what we need to fix is: (a) prevent the next deploy from
stepping on the same rake, (b) understand and eliminate the root
cause.

#### 6.3.1. Stop the bleeding

```bash
# 1. Freeze the prod deploy pipeline (GitHub UI):
#    Actions → "Deploy Cloud" workflow → ··· → Disable workflow
#    (or via API:)
gh api -X PUT \
  /repos/larchanka-training/dmc-1-t2-notebook-mono/actions/workflows/deploy-cloud.yml/disable

# 2. Confirm the service rolled back and is stable on the old revision
aws ecs describe-services --cluster jsnotes-t2 --services jsnotes-t2-api \
  --query 'services[0].{TD:taskDefinition,Desired:desiredCount,Running:runningCount,RolloutState:deployments[0].rolloutState}' \
  --output table
# Expectation: rolloutState=COMPLETED, Running==Desired
```

#### 6.3.2. Diagnose root cause

```bash
# Compare the failed revision vs the previous one (what changed in env/secrets/image)
FAILED_TD_ARN=$(aws ecs describe-services --cluster jsnotes-t2 \
  --services jsnotes-t2-api \
  --query 'services[0].deployments[?status==`FAILED`] | [0].taskDefinition' \
  --output text)

# If FAILED_TD_ARN is empty — events may have aged out of describe-services,
# look at the history of TD revisions:
aws ecs list-task-definitions --family-prefix jsnotes-t2-api \
  --sort DESC --max-items 5 --output table

# Inspect the failed revision
aws ecs describe-task-definition --task-definition "$FAILED_TD_ARN" \
  --query 'taskDefinition.containerDefinitions[0].{Image:image,Env:environment,Secrets:secrets[].name}' \
  --output json
```

5 typical B1 classes that the runbook covers explicitly:

| B1 class                                  | How to fix                                  |
|--------------------------------------------|---------------------------------------------|
| Missing Secrets Manager value (as in the incident after `larchanka-training/dmc-1-t2-notebook-mono#118`) | §6.3.3 — set the secret value, redeploy |
| Secret ARN in the TD is stale (was removed/replaced) | Roll back the TD or fix Terraform, see §6.3.4 |
| Wrong env value (e.g. `APP_ENV=dev` in prod) | Roll back the TD revision, fix in Terraform |
| IAM execution role lost permission for the secret | Fix the inline policy, redeploy           |
| ECR image tag does not exist / wrong image_tag | Roll back via `workflow_dispatch` with the previous SHA |

#### 6.3.3. Setting a missing Secrets Manager value (as in the incident after `larchanka-training/dmc-1-t2-notebook-mono#118`)

```bash
# Example: RESEND_API_KEY is missing
aws secretsmanager describe-secret --secret-id jsnotes-t2-resend-api-key \
  --query '{LastChanged:LastChangedDate,VersionsToStages:VersionIdsToStages}' \
  --output json
# If VersionsToStages is empty / only an initial placeholder — the value was never set

# Request the key from the Resend account owner (the instructor), then:
aws secretsmanager put-secret-value --secret-id jsnotes-t2-resend-api-key \
  --secret-string "re_xxxxxxxxxxxxxxxxxxxxxxxxx"

aws secretsmanager put-secret-value --secret-id jsnotes-t2-email-from \
  --secret-string "noreply@jsnb.org"
# (EMAIL_FROM must be a verified sender in Resend)

# Redeploy the same task definition (force-new-deployment) — it will
# pick up the fixed secret value via the execution role
aws ecs update-service --cluster jsnotes-t2 --service jsnotes-t2-api \
  --force-new-deployment

aws ecs wait services-stable --cluster jsnotes-t2 --services jsnotes-t2-api
```

#### 6.3.4. Roll the task definition back to a previous known-good revision

If the service is still on the bad revision (rare — the circuit
breaker usually rolled back already), or if pinning to a previous
revision is explicitly required:

```bash
# List the last 5 revisions
aws ecs list-task-definitions --family-prefix jsnotes-t2-api \
  --sort DESC --max-items 5

PREV_TD_ARN="arn:aws:ecs:eu-north-1:867633231218:task-definition/jsnotes-t2-api:<N>"

aws ecs update-service --cluster jsnotes-t2 --service jsnotes-t2-api \
  --task-definition "$PREV_TD_ARN" \
  --force-new-deployment

aws ecs wait services-stable --cluster jsnotes-t2 --services jsnotes-t2-api
```

#### 6.3.5. Unfreeze the pipeline

After Verify (§6.6) — re-enable the workflow:

```bash
gh api -X PUT \
  /repos/larchanka-training/dmc-1-t2-notebook-mono/actions/workflows/deploy-cloud.yml/enable
```

### 6.4. B2 — Code crash recovery

The new image rolled out but crashes (on startup or at runtime).
Unlike B1, this is a **code problem**, not configuration. Fix it by
rolling back to the previous immutable `sha-<short>` via
`deploy-cloud.yml workflow_dispatch`.

#### 6.4.1. Find the previous "good" SHA

```bash
# The currently active (bad) image
ACTIVE_TD=$(aws ecs describe-services --cluster jsnotes-t2 \
  --services jsnotes-t2-api --query 'services[0].taskDefinition' --output text)
BAD_IMAGE=$(aws ecs describe-task-definition --task-definition "$ACTIVE_TD" \
  --query 'taskDefinition.containerDefinitions[0].image' --output text)
echo "BAD image: $BAD_IMAGE"
# Example: 867633231218.dkr.ecr.eu-north-1.amazonaws.com/jsnotes-t2:api-sha-ce8f4c9

# Previous SHAs from git log on main (roll back to the "last known good")
git -C ~/.../dmc-1-t2-notebook-mono log --oneline main -n 10
# Alternative: ECR list, sorted by pushedAt desc
aws ecr describe-images --repository-name jsnotes-t2 \
  --filter tagStatus=TAGGED \
  --query 'sort_by(imageDetails, &imagePushedAt)[-10:].{Tags:imageTags,Pushed:imagePushedAt}' \
  --output table | grep 'api-sha-'
```

Pick the previous immutable `api-sha-<short>` that you know was green
(e.g. the last tag before the bad merge).

#### 6.4.2. Rollback via workflow_dispatch

```bash
GOOD_SHA="sha-de50503"  # example; substitute the real short SHA from ECR

# Run deploy-cloud.yml with the specific tag
gh workflow run deploy-cloud.yml \
  --ref main \
  -f image_tag="$GOOD_SHA"

# Watch the run
gh run watch
```

`deploy-cloud.yml` (as described in `AGENTS.md` §6):

- registers a new TD revision from the Terraform baseline, swapping
  the image to `api-${GOOD_SHA}`;
- runs migrations as a one-off ECS task (for a code rollback the
  migration is usually a no-op — unless the rollback crosses a
  schema-changing changeset, see §6.4.4);
- rolling update of ECS;
- waits for `services-stable`;
- fails red if the circuit breaker rolled back.

#### 6.4.3. If the pipeline is unavailable — manual rollback

```bash
# Copy env/secrets/IAM from the baseline TD, swap only the image
GOOD_IMAGE="867633231218.dkr.ecr.eu-north-1.amazonaws.com/jsnotes-t2:api-${GOOD_SHA}"

# Get the baseline TD from Terraform output (intended state, not active)
cd terraform/cloud
BASE_TD_ARN=$(terraform output -raw api_task_definition_arn)

# Make a copy with the image substituted (jq):
NEW_TD_INPUT=$(aws ecs describe-task-definition --task-definition "$BASE_TD_ARN" \
  --query 'taskDefinition' --output json | \
  jq --arg img "$GOOD_IMAGE" '
    .containerDefinitions[0].image = $img |
    del(.taskDefinitionArn, .revision, .status, .requiresAttributes, .compatibilities, .registeredAt, .registeredBy)
  ')

NEW_TD_ARN=$(echo "$NEW_TD_INPUT" | aws ecs register-task-definition \
  --cli-input-json file:///dev/stdin \
  --query 'taskDefinition.taskDefinitionArn' --output text)

aws ecs update-service --cluster jsnotes-t2 --service jsnotes-t2-api \
  --task-definition "$NEW_TD_ARN" --force-new-deployment

aws ecs wait services-stable --cluster jsnotes-t2 --services jsnotes-t2-api
```

#### 6.4.4. If the bad SHA already applied a schema-changing migration

Liquibase is forward-only: a code rollback does not roll the schema
back. Then:

1. Check `databasechangelog` (§5.4.3) for which changeset the bad
   deploy applied.
2. If the old code **does not need** the new columns/tables — a
   rollback is safe (the old code simply does not use them).
3. If the old code **breaks** on the new schema — you need a forward
   fix changeset, not a rollback. This is no longer a Sev-1 incident,
   it is a hot-fix via PR.

### 6.5. CloudFront → ALB origin issue (rare)

CloudFront returns 5xx but ALB direct responds with 200. Possible
causes:

- CloudFront cache is serving a stale 5xx response → invalidation;
- the `ordered_cache_behavior` for `/api/v1/*` broke after a Terraform
  change;
- the ALB origin DNS changed (ALB was re-created → new DNS).

```bash
# Invalidate the cache for the API path
DIST_ID="E29EW3R1X0PB5W"  # confirm via list-distributions
aws cloudfront create-invalidation --distribution-id "$DIST_ID" \
  --paths "/api/v1/*"

# Verify the ALB origin points to the current ALB DNS
aws cloudfront get-distribution-config --id "$DIST_ID" \
  --query 'DistributionConfig.Origins.Items[?Id==`api-alb`].DomainName' \
  --output text

# Compare with the real ALB DNS
aws elbv2 describe-load-balancers --names jsnotes-t2-alb \
  --query 'LoadBalancers[0].DNSName' --output text
```

If the DNS values differ → `terraform apply` to sync (leave the freeze
mode) or a manual CloudFront origin update.

### 6.6. Verify

1. Basic smoke (§2.3).
2. Additional for B:

```bash
# ECS rolled out without new rollback events
aws ecs describe-services --cluster jsnotes-t2 --services jsnotes-t2-api \
  --query 'services[0].deployments' --output json
# Expectation: exactly one deployment, rolloutState=COMPLETED

# Health via ALB direct
ALB_DNS=$(aws elbv2 describe-load-balancers --names jsnotes-t2-alb \
  --query 'LoadBalancers[0].DNSName' --output text)
curl -fsS "http://${ALB_DNS}/api/v1/health"

# Fresh logs without startup/runtime errors
aws logs tail /ecs/jsnotes-t2-api --since 5m \
  --filter-pattern '?ERROR ?Exception ?Traceback' | head -50
# Expectation: empty
```

### 6.7. RTO / RPO

| Sub-scenario | RTO (target) | RPO |
|--------------|--------------|-----|
| B1 missing secret value | 15–25 min (put-secret-value + force-new-deployment) | 0 |
| B1 TD revision rollback | 10–15 min (update-service + wait) | 0 |
| B2 rollback via workflow_dispatch | 15–25 min (deploy-cloud.yml run + migrations + roll) | 0 (migrations are forward-only, see §6.4.4) |
| B2 manual rollback | 10–20 min (register-task-definition + update-service) | 0 |
| CloudFront cache stale | 5–10 min (invalidation propagation) | 0 |

RPO = 0 because B incidents do not lose data (unless they coincide
with A4, in which case you follow both).

### 6.8. Follow-ups

- **Pre-deploy secret check** in `infra-cloud.yml`: if
  `aws secretsmanager get-secret-value` returns empty/placeholder —
  fail the infra apply earlier than the deploy hits it. Partially
  implemented (see the 14.06 summary), extend to all 4 auth secrets.
- **CloudWatch alarm** on the `ECS-ServiceDeploymentFailed` event
  (via an EventBridge rule → SNS).
- **CloudWatch metric filter** on `/ecs/jsnotes-t2-api` for the
  pattern `"validation error"` / `"missing required environment
  variable"` → counter → alarm.
- **`gh workflow run` checklist** in Prerequisites — which `GH_PAT`
  scope is required to run `deploy-cloud.yml` dispatch.

---

## 7. Scenario C — AWS region outage

**Severity:** Sev-1 (full outage) / Sev-2 (degraded). TTD: 5–30
minutes (AWS Health page or user report).

The `eu-north-1` region becomes unavailable or strongly degraded.

### 7.1. Honest caveat

**Multi-region disaster recovery is out of scope** for the current
educational setup:

- the infra is deployed only in `eu-north-1`;
- there is no cross-region RDS replication / snapshot copy;
- there is no cross-region ECR image replication;
- there is no cross-region failover for the ALB/CloudFront origin
  (CloudFront is global, but the origin is single);
- the ACM cert and Cloudflare DNS are global/external — they move
  "for free".

The goal of this section is to **minimize downtime and data loss**,
not to achieve a near-zero RTO. If high availability matters — that
is an architecture-level task (Tech Lead month 2 roadmap).

### 7.2. Identify

```bash
# 1. AWS Service Health (region-wide)
#    https://health.aws.amazon.com/health/status
#    If eu-north-1 → degraded / outage → confirmation of C.

# 2. From another region: can the AWS API in eu-north-1 respond at all?
AWS_REGION=eu-north-1 aws ecs describe-services \
  --cluster jsnotes-t2 --services jsnotes-t2-api 2>&1 | head -20
# If timeout / 5xx from api.ecs.eu-north-1.amazonaws.com → region issue.

# 3. CloudFront status (it is global — should stay up even if origin is down)
curl -fsS -o /dev/null -w "CloudFront edge: %{http_code} %{time_total}s\n" \
  https://jsnb.org/static/  # static path bypasses the ALB origin

# 4. Cloudflare DNS status (if jsnb.org does not resolve — it is
#    Cloudflare, not AWS)
dig +short jsnb.org
```

### 7.3. Scope decision

| What is down                                          | Actions |
|--------------------------------------------------------|---------|
| Region fully down, no ETA from AWS                     | §7.4 — manual cross-region redeploy to a new region (RTO days) |
| Region degraded, ETA < 4 hours                         | §7.5 — wait + user communication, no action |
| Only one service (e.g. RDS) is degraded                 | go back to §5 / §6 for the specific component  |
| eu-north-1 OK, but a CloudFront global edge issue       | §7.6 — user message, wait for AWS |

90% of the time this is §7.5 (wait), not §7.4 (manual rebuild).

### 7.4. Manual cross-region redeploy (if the region does not return)

This is the **last resort**, takes days, and requires the AWS account
owner (the instructor). Steps:

1. **Declare a major incident**, communicate to users an expected
   wait of days.
2. **Freeze**: disable all workflows (`infra-cloud.yml`,
   `deploy-cloud.yml`, ECR publish).
3. **Choose a target region** among those where the Bedrock EU Geo
   profile is available: `eu-central-1`, `eu-west-1`, `eu-west-3`.
4. **Copy ECR images into the target region:**
   ```bash
   aws ecr describe-images --repository-name jsnotes-t2 \
     --region eu-north-1 --filter tagStatus=TAGGED \
     --query 'sort_by(imageDetails, &imagePushedAt)[-5:].imageTags' \
     > tags.json
   # Pull the last-good images locally, push to the target region's ECR.
   # Or (preferable) copy via AWS CLI (cross-region ECR replication
   # requires an ECR replication rule — we do not have one → manual).
   ```
5. **Restore RDS from a cross-region snapshot copy** — but a snapshot
   copy to the target region is not configured. Without it, RDS has to
   be restored from the latest exported dump (if any; see §11.2
   off-boarding checklist). RPO = time since the last dump
   (potentially days).
6. **Re-apply Terraform in the new region:**
   ```bash
   cd terraform/cloud
   AWS_REGION=eu-central-1 terraform apply \
     -var "aws_region=eu-central-1"
   ```
   The ACM cert has to be re-created in `us-east-1` (where it already
   lives), the `jsnb.org`/`www.jsnb.org` aliases need to be switched
   in Cloudflare to the new CloudFront domain.
7. **Restore secrets** (the values are held in the archive — see §11.2).
8. **Re-run Liquibase migrations** against the restored RDS.
9. **Smoke** (§2.3).

**RTO:** ≥ 24 hours. **RPO:** up to the last exported dump.

### 7.5. Wait + communication (the typical case)

If AWS promises recovery within hours — just wait, do not make hot
moves:

1. User-facing message on `jsnb.org` (static HTML on CloudFront —
   replace the default S3 object with a maintenance page):
   ```bash
   aws s3 cp ./maintenance.html s3://jsnotes-t2-frontend/index.html \
     --cache-control 'max-age=60' --content-type 'text/html'
   aws cloudfront create-invalidation --distribution-id E29EW3R1X0PB5W \
     --paths '/' '/index.html'
   ```
2. Twitter / team email → announcement with ETA from AWS.
3. Monitor AWS Health every 30 minutes.
4. After recovery — `aws s3 sync` the normal UI build back.

### 7.6. CloudFront global edge issue

Very rare: a CloudFront edge itself degrades. Actions:

- check across several edge locations (`https://www.whatsmydns.net/`
  or `curl --resolve jsnb.org:443:<edge-ip>` from different VPNs);
- if only one edge is red → AWS will reroute traffic;
- if all edges are red → wait.

There is no user-facing fix: we do not control the global CDN.

### 7.7. Follow-ups (Scenario C hardening)

To turn Scenario C from "days" into "hours" we need (not part of this
runbook, a separate task):

- **Cross-region RDS snapshot copy** — automated daily/weekly copy to
  a second region (`eu-west-1`). Cost ≈ $5/month for storage.
- **ECR cross-region replication rule** — configured via Terraform,
  zero cost for small images.
- **Bedrock cross-region readiness** — the Nova EU Geo profile already
  includes 4 regions; we need to make sure the IAM task role allows
  invoke in each one.
- **Pre-baked Terraform var sets** for each target region.
- **Bilingual maintenance page** in S3 (always ready to deploy).

---

## 8. Scenario D — Secret leak

**Severity:** Sev-1 for all classes (AWS deploy key, JWT, DB pwd,
Resend, GH_PAT, Cloudflare token). TTD: minutes (GitHub secret-scan) —
**weeks** (if reported externally). The widest TTD spread of all
scenarios.

A key / password / token leaks: pushed to a public repository, shown
in a screenshot, sent to the wrong Slack, observed in third-party
logs, or reported via bug bounty.

This is **Sev-1**, regardless of whether abuse has already happened:
time-to-rotate determines the blast radius.

### 8.0. ⚠ Cascade scenario: AWS deploy-user key (HIGHEST priority)

**A leak of `AWS_ACCESS_KEY_ID` for `deploy-user` is the most
dangerous**, because:

1. `deploy-user` has `SecretsManagerReadWrite` → it can read **all**
   secrets in the account (see `docs/aws-cloud-migration.md`,
   `_private/notes/sprint3/infra-baseline.md` §4):
   `JWT_SECRET`, `OTP_HASH_SECRET`, `RESEND_API_KEY`, `EMAIL_FROM`,
   `DATABASE_URL`, `db-migration`. → **All of them must be considered
   compromised.**
2. `deploy-user` can **deploy** via `deploy-cloud.yml` → an attacker
   can push a malicious image to prod.
3. **Account shared with T1** (§1.1) → a leak affects T1's resources
   too. → **Mandatory notification to T1 + AWS admin (the instructor)**.

So recovery is **not a single rotation but a cascade**.

#### Cascade procedure

```bash
# Step 0. Notify T1 + AWS admin (the instructor). Use the escalation
#         chain in §1.2. WITHOUT this step the cascade is incomplete.

# Step 1. Stop the bleeding — deactivate the key (do NOT delete)
aws iam update-access-key --user-name deploy-user \
  --access-key-id AKIA<LEAKED> --status Inactive

# Step 2. Freeze deploy + infra pipelines in monorepo
gh api -X PUT \
  /repos/larchanka-training/dmc-1-t2-notebook-mono/actions/workflows/deploy-cloud.yml/disable
gh api -X PUT \
  /repos/larchanka-training/dmc-1-t2-notebook-mono/actions/workflows/infra-cloud.yml/disable
gh api -X PUT \
  /repos/larchanka-training/dmc-1-t2-notebook-mono/actions/workflows/ecr-publish.yml/disable

# Step 3. Create a new key and update GitHub Secrets
NEW_KEYS=$(aws iam create-access-key --user-name deploy-user)
# Update in the GitHub UI Secrets (mono, api, ui) — NOT via CLI.

# Step 4. CloudTrail audit for the period from leak to deactivate
LEAK_TIME="2026-06-17T08:00:00Z"
DEACT_TIME="2026-06-17T10:30:00Z"
aws cloudtrail lookup-events \
  --lookup-attributes AttributeKey=Username,AttributeValue=deploy-user \
  --start-time "$LEAK_TIME" --end-time "$DEACT_TIME" \
  --query 'Events[].{Time:EventTime,Event:EventName,Source:SourceIPAddress}' \
  > /tmp/audit-leak.json

# Pay special attention to GetSecretValue / PutSecretValue / RegisterTaskDefinition.

# Step 5. Cascade rotation of all secrets that could have been read:
#   §8.3.3 JWT_SECRET
#   §8.3.4 OTP_HASH_SECRET
#   §8.3.5 DB password (+ DATABASE_URL and db-migration updates)
#   §8.3.2 RESEND_API_KEY (via Marat)
# Each runs SEQUENTIALLY with verify in between.

# Step 6. After the cascade — verify the pipeline with the new keys:
gh workflow run infra-cloud.yml --ref main  # plan no-op
gh workflow run deploy-cloud.yml --ref main -f image_tag=<current sha>

# Step 7. ONLY AFTER a green pipeline — delete the old key
aws iam delete-access-key --user-name deploy-user --access-key-id AKIA<LEAKED>

# Step 8. Unfreeze the pipelines
gh api -X PUT \
  /repos/larchanka-training/dmc-1-t2-notebook-mono/actions/workflows/deploy-cloud.yml/enable
gh api -X PUT \
  /repos/larchanka-training/dmc-1-t2-notebook-mono/actions/workflows/infra-cloud.yml/enable
gh api -X PUT \
  /repos/larchanka-training/dmc-1-t2-notebook-mono/actions/workflows/ecr-publish.yml/enable

# Step 9. Postmortem + T1 + AWS admin update — mandatory for a
#         shared-account incident.
```

**RTO for the full cascade:** 2–4 hours (5 min to deactivate + 1 hour
of cascade rotations + 1 hour of verify + buffer).

**RPO:** 0 for data, but **time-of-exposure damage can be > 0** (an
attacker may already have read something).

### 8.1. Identify

First — what exactly leaked and where:

| Leak class                                | Signs                                            |
|--------------------------------------------|--------------------------------------------------|
| AWS access key (`AKIA…`)                   | GitHub leak alert; CloudTrail unusual API calls; an unexpected bill |
| `JWT_SECRET`                                | API logs with unexpected token claims; user-reported account access |
| `OTP_HASH_SECRET`                           | An unusual pattern in OTP attempts               |
| `RESEND_API_KEY`                            | Email in the Resend dashboard we did not send; a new verified sender |
| DB password / `DATABASE_URL`                | RDS connections from unknown IPs in the logs    |
| `GH_PAT`                                    | GitHub audit log → API calls from an unknown app |
| Cloudflare API token                        | DNS changes we did not make                      |

```bash
# 1. GitHub secret-scan notification
gh api /repos/larchanka-training/dmc-1-t2-notebook-mono/secret-scanning/alerts \
  --jq '.[] | {created:.created_at,secret_type,state,locations:.locations_url}'

# 2. AWS CloudTrail (last hour) — unusual API calls
aws cloudtrail lookup-events --max-results 50 \
  --lookup-attributes AttributeKey=EventName,AttributeValue=ConsoleLogin \
  --query 'Events[].{Time:EventTime,User:Username,Region:AwsRegion,Source:SourceIPAddress}' \
  --output table

# 3. RDS connections not from the ECS SG
aws rds describe-events --source-identifier jsnotes-t2-db \
  --source-type db-instance --duration 60 --output table

# 4. API login history (if the claim is "access to someone else's notebooks")
aws logs filter-log-events --log-group-name /ecs/jsnotes-t2-api \
  --start-time $(date -u -v -1H +%s)000 \
  --filter-pattern '"unauthorized" "auth_failed" "invalid_token"' \
  | jq -r '.events[].message' | head -50
```

### 8.2. Decide rotation order

```
1. The compromised secret → revoke / rotate first (stop the bleeding)
2. Related (cascading) secrets → rotate next
3. Sessions/tokens signed with the old secret → invalidate
4. Audit for the leak-to-rotation period → detect abuse
```

Cascading examples:

- AWS access key → re-issue → rotate **all** secrets that could have
  been read with that key during the exposure window (see CloudTrail).
- DB password → re-issue → update `DATABASE_URL` and `db-migration`
  secrets → roll API tasks → consider a **full audit** of the
  notebooks tables.
- `JWT_SECRET` → new → **invalidates ALL user sessions** (this is a
  user-facing decision, see §8.3.3).

### 8.3. Rotation procedures by class

#### 8.3.1. AWS access key (`AKIA…`) leaked

The most common scenario: the key got pushed to git.

```bash
# Step 1. In the AWS IAM Console: find the user owning the key
aws iam list-access-keys --user-name deploy-user

# Step 2. Deactivate the compromised key (do NOT delete immediately —
# delete can break the pipeline; deactivate is reversible, delete is not)
aws iam update-access-key --user-name deploy-user \
  --access-key-id AKIA<LEAKED> --status Inactive

# Step 3. Create a new key
NEW_KEYS=$(aws iam create-access-key --user-name deploy-user)
echo "$NEW_KEYS" | jq -r '.AccessKey | "AccessKeyId: \(.AccessKeyId)\nSecretAccessKey: \(.SecretAccessKey)"'

# Step 4. Update GitHub Secrets — NOT via CLI (the value would land in
# shell history). Via the GitHub UI:
#   Settings → Secrets and variables → Actions →
#   AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY → Update
# Repos: mono, api, ui — all three (preview workflows use them).

# Step 5. Verify the pipeline passes with the new keys:
#   - run `infra-cloud.yml` workflow_dispatch (no-op plan);
#   - run `deploy-cloud.yml` workflow_dispatch with the current sha;
#   - wait for green.

# Step 6. Only after a successful green pipeline — delete the old key
aws iam delete-access-key --user-name deploy-user --access-key-id AKIA<LEAKED>

# Step 7. CloudTrail audit for the period from leak to deactivation
LEAK_TIME="2026-06-17T08:00:00Z"
DEACT_TIME="2026-06-17T10:30:00Z"
aws cloudtrail lookup-events \
  --lookup-attributes AttributeKey=Username,AttributeValue=deploy-user \
  --start-time "$LEAK_TIME" --end-time "$DEACT_TIME" \
  --query 'Events[].{Time:EventTime,Event:EventName,Source:SourceIPAddress}' \
  --output json > /tmp/audit-leak.json

# Step 8. Review for unusual API calls (those that differ from the
# normal pipeline pattern). If any — escalate to the AWS account owner.
```

#### 8.3.2. RESEND_API_KEY leaked

Escalation: the Resend account owner is Marat G. (see §1.2). The
rotation is performed by him.

```bash
# Step 1. In the Resend dashboard (https://resend.com/api-keys):
#   - Revoke the compromised key;
#   - Generate a new one with the same scope (sending only);
#   - Copy the one-time value.

# Step 2. Update Secrets Manager with the new value
aws secretsmanager put-secret-value --secret-id jsnotes-t2-resend-api-key \
  --secret-string "$(read -s -p 'paste new key: ' k && echo "$k")"

# Step 3. Force-new-deployment for ECS — new tasks pick up the new key
aws ecs update-service --cluster jsnotes-t2 --service jsnotes-t2-api \
  --force-new-deployment
aws ecs wait services-stable --cluster jsnotes-t2 --services jsnotes-t2-api

# Step 4. In the Resend dashboard check Sent → no emails sent that we
# did not initiate during the exposure window. If any — flag to Resend
# support + warn users with potentially affected addresses.

# Step 5. Update GitHub Secrets → RESEND_API_KEY (for the
# infra-cloud.yml bootstrap). Via the UI, not the CLI.
```

#### 8.3.3. `JWT_SECRET` leaked — INVALIDATES ALL SESSIONS

This is the most user-painful leak class: rotation **kicks all users
out**.

```bash
# Step 1. Communication BEFORE rotation: tell users
#   ("at HH:MM we will forcibly restart auth, you will need to sign in
#    again, your notebooks will not be affected") — even if there are
#   only a few users.

# Step 2. Generate a new key ≥ 32 bytes
NEW=$(openssl rand -base64 48)
echo "$NEW" | wc -c   # must be ≥ 32

# Step 3. Set the new value
aws secretsmanager put-secret-value --secret-id jsnotes-t2-jwt-secret \
  --secret-string "$NEW"

# Step 4. Force-new-deployment for ECS
aws ecs update-service --cluster jsnotes-t2 --service jsnotes-t2-api \
  --force-new-deployment
aws ecs wait services-stable --cluster jsnotes-t2 --services jsnotes-t2-api

# Step 5. All access tokens signed by the old secret are now rejected.
# Refresh tokens too (they are validated against the same key). Users
# will see 401 → the UI redirects to login → OTP again.

# Step 6. In the logs for the leak-to-rotation period — search for
# unauthorized access patterns (see §8.1, query 4).

# Step 7. unset NEW (do not keep it in shell history)
unset NEW
history -c 2>/dev/null || true
```

#### 8.3.4. `OTP_HASH_SECRET` leaked

The OTP hash secret is the pepper used to hash OTP codes in the DB. A
leak lets an attacker generate a valid hash → bypass OTP validation.

```bash
# Step 1. Generate a new one
NEW=$(openssl rand -base64 48)

# Step 2. Set the new value
aws secretsmanager put-secret-value --secret-id jsnotes-t2-otp-hash-secret \
  --secret-string "$NEW"

# Step 3. NOTE: all pending OTPs in the DB (rows in `users.otps` with
# `confirmed_at IS NULL`) become invalid — users who requested an OTP
# before the rotation cannot use it to sign in. They must request a
# new one. This is short-term breakage (5–15 minutes).
# Optionally: TRUNCATE pending OTPs via psql to avoid confusion.

# Step 4. Force-new-deployment for ECS
aws ecs update-service --cluster jsnotes-t2 --service jsnotes-t2-api \
  --force-new-deployment
unset NEW
```

#### 8.3.5. DB password leaked

> ⚠ **Brief failure window.** Between steps 1 and 3 the running
> API tasks still have the old password (in their env, cached from
> the old secret), while RDS already rejects it. This is an **expected
> short downtime of 2–5 minutes**. Lambda-based secret rotation is not
> configured. The order below minimizes the window but does not
> eliminate it entirely.

```bash
# Step 1. Change the RDS master password (apply-immediately)
NEW_PASS=$(openssl rand -base64 24 | tr -d '/+=')  # URL-safe

aws rds modify-db-instance --db-instance-identifier jsnotes-t2-db \
  --master-user-password "$NEW_PASS" --apply-immediately

# Wait (1–3 minutes)
aws rds wait db-instance-available --db-instance-identifier jsnotes-t2-db

# Step 2. Get the endpoint and assemble the new secret strings
EP=$(aws rds describe-db-instances --db-instance-identifier jsnotes-t2-db \
  --query 'DBInstances[0].Endpoint.Address' --output text)

aws secretsmanager put-secret-value --secret-id jsnotes-t2-database-url \
  --secret-string "postgresql://jsnotes:${NEW_PASS}@${EP}/wiki"

aws secretsmanager put-secret-value --secret-id jsnotes-t2-db-migration \
  --secret-string "$(jq -n --arg u "jsnotes" --arg p "$NEW_PASS" \
    --arg url "jdbc:postgresql://${EP}/wiki" \
    '{username:$u,password:$p,url:$url}')"

# Step 3. Roll the API
aws ecs update-service --cluster jsnotes-t2 --service jsnotes-t2-api \
  --force-new-deployment
aws ecs wait services-stable --cluster jsnotes-t2 --services jsnotes-t2-api

# Step 4. Audit RDS connections for the exposure window (requires RDS
# logs if performance insights are enabled). Without them — only
# CloudWatch RDS metrics for abnormal connection counts.

unset NEW_PASS
```

**Drift note:** Terraform owns `random_password.db.result`. After a
manual rotation a drift in `aws_db_instance.this.password` appears.
Reconcile via a separate PR (regenerate in Terraform or import the
new password into state).

#### 8.3.6. GH_PAT leaked

```bash
# Step 1. In the GitHub UI:
#   Settings → Developer settings → Personal access tokens →
#   find the token → Revoke

# Step 2. Create a new PAT (fine-grained preferable):
#   - Repos: mono / api / ui (read+write);
#   - Workflows: read;
#   - Expiration: 90 days.

# Step 3. Update GitHub Secrets `GH_PAT` in all 3 repos (mono/api/ui).

# Step 4. Audit:
gh api /user/audit-log --paginate \
  --jq '.[] | select(.created_at > "2026-06-17T08:00:00Z") | {created:.created_at,action,actor,repo}'
# (available only for Enterprise; for personal accounts — Settings →
#  Security → Audit log)
```

#### 8.3.7. Cloudflare API token / DNS credential leaked

Escalation: the `jsnb.org` domain owner is Marat G. (§1.2).

```bash
# Step 1. Cloudflare dashboard → My Profile → API Tokens →
#   Revoke the compromised one → create a new one.

# Step 2. Check the DNS audit log (Dashboard → Audit Logs) for changes
# during the exposure window.

# Step 3. Verify that all DNS records for jsnb.org are intact:
dig +short jsnb.org A
dig +short www.jsnb.org A
dig +short jsnb.org TXT  # SPF / DKIM not tampered with
```

If someone changed an A record or MX record during the exposure
window — this is an **escalation to Sev-1**: the attacker could have
collected OTPs sent to our verified senders, or redirected jsnb.org
traffic to their own server.

### 8.4. Verify

After any rotation:

1. Basic smoke (§2.3).
2. Confirm ECS tasks are fresh (the new secrets are picked up):
   ```bash
   aws ecs describe-services --cluster jsnotes-t2 --services jsnotes-t2-api \
     --query 'services[0].deployments[?status==`PRIMARY`].{TD:taskDefinition,Started:createdAt,Status:rolloutState}' \
     --output json
   ```
3. Verify the compromised value no longer works (try to use the old
   JWT / OTP / API key and confirm → 401).
4. CloudTrail / GitHub audit log — no further abuse.

### 8.5. Postmortem

A key leak **mandatorily** requires a postmortem:

- **How long** the key was exposed (leak → deactivation).
- **What the attacker could do** during that time.
- **What we did** — was there abuse, what scope.
- **Why it leaked** — root cause (git push without `.gitignore`,
  screenshot in a public chat, etc.).
- **What we change** — pre-commit hooks for gitleaks, scheduled
  rotation, principle of least privilege.

Template — §12.

### 8.6. RTO / RPO

| Leak class                  | RTO to stop-the-bleeding | RTO to full recovery |
|------------------------------|--------------------------|----------------------|
| AWS access key               | 5 min (deactivate)        | 30–60 min (rotate + pipeline verify) |
| `JWT_SECRET`                 | 10 min                    | 15 min + user re-login |
| `OTP_HASH_SECRET`            | 10 min                    | 15 min                  |
| `RESEND_API_KEY`             | 5 min (revoke in Resend)  | 20 min                  |
| DB password                  | 5 min (RDS modify)        | 15–25 min                |
| GH_PAT                       | 1 min (revoke in GH UI)   | 10 min                  |
| Cloudflare token             | 1 min                     | 10 min + DNS audit       |

RPO = 0 for all classes (rotation does not lose anything except
sessions for `JWT_SECRET`).

### 8.7. Follow-ups

- **`gitleaks` pre-commit hook** in the lefthook config (mono/api/ui).
- **GitHub secret scanning** (enabled by default for public, check it
  for the private organization).
- **Scheduled rotation of JWT_SECRET / OTP_HASH_SECRET** every 90 days
  (with user communication).
- **Audit log centralization** — export CloudTrail to S3 for long-term
  storage (beyond the 90-day AWS window).
- **The "no `get-secret-value` in regular work" principle** — the
  runbook makes it explicit: `describe-secret` (metadata) is enough,
  reading the value is not allowed outside an incident.

---

## 9. Scenario E — Bedrock budget / limit exceeded

**Severity:** Sev-2 when approaching the budget; Sev-1 on a confirmed
abuse attack. **TTD: up to 24+ hours (the worst in the project)** —
proactive alerting is currently absent, see §9.0.

LLM spend on Bedrock has spiked or is approaching the budget. It can
be due to legitimate growth, abuse (someone found a way around the
auth/rate limit), or a backend bug (e.g. a retry loop without
exponential backoff).

### 9.0. ⚠ Detection gap — current reality

**Today an overrun is detected only manually and with significant
delay:**

- AWS Budget alert is **absent** (not in Terraform, see
  `_private/notes/sprint3/infra-baseline.md` §8; `deploy-user` lacks
  the `budgets:ModifyBudget` permission).
- Cost Explorer updates with a **lag of 24–48 hours**.
- AWS Bedrock CloudWatch metrics `Invocations` are available near
  real-time, but with no alarm nobody looks at them.
- The realtime signal is only throttling (when AWS has already started
  rejecting requests), which means "production is already broken".

#### Interim detection within deploy-user's scope — recommendation

The API already writes `prompt_tokens` and `completion_tokens` in
structured logs for every LLM request (`docs/ai-architecture.md`).
That makes a **CloudWatch Logs metric filter + alarm** possible, which
does **not** require account-level `budgets:*` rights (only
`logs:PutMetricFilter` and `cloudwatch:PutMetricAlarm` — both within
`deploy-user`'s scope).

Terraform skeleton (for a separate follow-up PR):

```hcl
resource "aws_cloudwatch_log_metric_filter" "llm_total_tokens" {
  name           = "${var.project}-llm-total-tokens"
  log_group_name = "/ecs/jsnotes-t2-api"
  pattern        = "{ $.event = \"llm.requested\" }"
  metric_transformation {
    name      = "LlmTotalTokens"
    namespace = "JsnotesT2/LLM"
    value     = "$.total_tokens"
    unit      = "Count"
  }
}

resource "aws_cloudwatch_metric_alarm" "llm_token_burst" {
  alarm_name          = "${var.project}-llm-token-burst"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "LlmTotalTokens"
  namespace           = "JsnotesT2/LLM"
  period              = 3600                    # 1 hour
  statistic           = "Sum"
  threshold           = 100000                  # calibrate after baseline
  alarm_actions       = [aws_sns_topic.alerts.arn]
}
```

This closes **the project's largest TTD gap**. Tracked as HIGH
PRIORITY in §9.8 follow-ups (above the standard CloudWatch alarms
setup).

### 9.1. Identify

```bash
# 1. AWS Cost Explorer — Bedrock usage for the last 7 days
#    UI: https://console.aws.amazon.com/cost-management/home → Cost Explorer
#    Group by: Service → filter "Amazon Bedrock"
#    Compare with the baseline (Sprint #3: ≈ $0.50–$2/day for 5–10 users)

# 2. CloudWatch metrics (if Bedrock invocation metrics are enabled)
aws cloudwatch get-metric-statistics \
  --namespace AWS/Bedrock \
  --metric-name Invocations \
  --start-time $(date -u -v -24H +%Y-%m-%dT%H:%M:%S) \
  --end-time $(date -u +%Y-%m-%dT%H:%M:%S) \
  --period 3600 --statistics Sum \
  --dimensions Name=ModelId,Value=eu.amazon.nova-lite-v1:0 \
  --output table

# Same for the guard model
aws cloudwatch get-metric-statistics \
  --namespace AWS/Bedrock \
  --metric-name Invocations \
  --start-time $(date -u -v -24H +%Y-%m-%dT%H:%M:%S) \
  --end-time $(date -u +%Y-%m-%dT%H:%M:%S) \
  --period 3600 --statistics Sum \
  --dimensions Name=ModelId,Value=eu.amazon.nova-micro-v1:0

# 3. Application logs: LLM requests for the last hour
aws logs filter-log-events \
  --log-group-name /ecs/jsnotes-t2-api \
  --start-time $(date -u -v -1H +%s)000 \
  --filter-pattern '"llm.requested"' \
  | jq -r '.events[].message' | head -100

# 4. Per-user distribution (anomaly check — is one user generating a lot?)
aws logs start-query --log-group-name /ecs/jsnotes-t2-api \
  --start-time $(date -u -v -24H +%s) --end-time $(date -u +%s) \
  --query-string 'filter event="llm.requested" | stats count() by user_id | sort count desc | limit 20'
# Save the queryId, then call get-query-results
```

### 9.2. Triage

| What you see                                           | Most likely  | Actions |
|--------------------------------------------------------|--------------|---------|
| Linear growth in Invocations, even per-user distribution | Legitimate growth | §9.3 — capacity planning, do not disable |
| Spike in Invocations + a single user_id dominates      | Single-user abuse / bug | §9.4.1 — block user + investigate |
| Spike + distribution across many user_ids              | Mass abuse or auth bypass | §9.4.2 — kill switch + security audit |
| Linear growth, **guard** invocations exceed generator  | Backend bug (guard looping) | §9.4.3 — code rollback (see §6 B2) |
| Cost grows without Invocations growth                   | Output tokens growing (long responses) | §9.4.4 — reduce max_tokens |

### 9.3. Capacity planning (not an emergency)

If the growth is legitimate, act in the normal order:

1. Record the new baseline in
   `_private/notes/sprint3/cost-baseline.md`.
2. Pass to Eng#2 (cost optimization) for re-calculation of the
   100/1k/10k scenarios.
3. If we are approaching $5/day (educational threshold) — flag the
   instructor as AWS billing owner.

Do not do anything reactive — the runbook is not needed.

### 9.4. Emergency actions

#### 9.4.1. Block single user

If a single user_id dominates:

> ⚠ **Architectural gap (2026-06-17):** the current `users.users`
> schema (see `api/app/modules/auth/models/user.py`) has **no**
> `disabled_at` / `is_active` / `banned_at` columns. The API does
> not check user status before a request. Therefore **blocking a
> single user in isolation is impossible without a code change**.
>
> Tracked: `larchanka-training/dmc-1-t2-notebook-api#73` (HIGH PRIORITY follow-up).

Workarounds available today:

| Option | Effect | When to apply |
|--------|--------|---------------|
| Hard delete the user row | Deletes the user + all their notebooks (CASCADE) | Confirmed bot/abuse, not a legitimate user |
| Rotate `JWT_SECRET` (§8.3.3) | Kicks **all** users out | Mass abuse when you cannot single out one |
| Cloud-agent kill switch (§9.4.2) | Stops Bedrock traffic for all | If the abuse is specifically on the LLM path |
| Wait for the PR with the `disabled_at` migration | 30–60 min | If the abuse is not critical in cost |

Hard delete commands (dangerous — irreversibly deletes data):

```bash
TASK=$(aws ecs list-tasks --cluster $ECS_CLUSTER --service-name $ECS_SERVICE \
  --desired-status RUNNING --query 'taskArns[0]' --output text)
aws ecs execute-command --cluster $ECS_CLUSTER --task "$TASK" \
  --container api --interactive --command "/bin/sh"

# Inside the container (psql may be unavailable in the production
# image, then use python+SQLAlchemy):
# psql "$DATABASE_URL" -c "DELETE FROM users.users WHERE id = '<USER_UUID>';"
```

In most cases the right order is **first** the kill switch (§9.4.2),
then a planned PR with the user-blocking migration.

#### 9.4.2. Cloud-agent kill switch (mass abuse)

When you do not know who is abusing but cost is growing catastrophically:
**turn off the Cloud agent entirely**. The in-browser WebLLM keeps
working for users whose browser supports it.

Level 1 — **app-level kill switch** (requires a code change!):

> ⚠ **Confirmed 2026-06-17 via live verification:** the
> `LLM_CLOUD_AGENT_ENABLED` env flag is **NOT present in `api/app/`
> nor in the active task definition** (revision 44 at check time).
> Therefore Level 1 below describes the **target/future state**, not
> a current capability.
>
> **Today in a real incident — use only Level 2** (IAM revoke) below.
> After the flag is implemented in the code + Terraform, Level 1 will
> become available.
>
> HIGH-priority follow-up: implement the flag (see §9.8).

```bash
# When the flag exists, set an env variable that disables the Cloud
# agent. Today (2026-06-17) it does NOT work. The current API does
# NOT check the LLM_CLOUD_AGENT_ENABLED variable.

# Via a task definition env (intent: a new TD revision with
# LLM_CLOUD_AGENT_ENABLED=false):
# The fastest path — `update-service` cannot override env without a
# new TD. So use `aws ecs register-task-definition` with a patch:

ACTIVE_TD=$(aws ecs describe-services --cluster jsnotes-t2 \
  --services jsnotes-t2-api --query 'services[0].taskDefinition' --output text)

NEW_TD_JSON=$(aws ecs describe-task-definition --task-definition "$ACTIVE_TD" \
  --query 'taskDefinition' --output json | \
  jq '.containerDefinitions[0].environment += [
        {"name":"LLM_CLOUD_AGENT_ENABLED","value":"false"}
      ] | del(.taskDefinitionArn, .revision, .status, .requiresAttributes,
              .compatibilities, .registeredAt, .registeredBy)')

KILL_TD_ARN=$(echo "$NEW_TD_JSON" | \
  aws ecs register-task-definition --cli-input-json file:///dev/stdin \
  --query 'taskDefinition.taskDefinitionArn' --output text)

aws ecs update-service --cluster jsnotes-t2 --service jsnotes-t2-api \
  --task-definition "$KILL_TD_ARN" --force-new-deployment

aws ecs wait services-stable --cluster jsnotes-t2 --services jsnotes-t2-api
```

After the kill switch is activated:

- `/api/v1/llm/generate` returns 503 `LLM_CLOUD_AGENT_DISABLED`;
- the UI should show a message and switch to the in-browser path (if
  available);
- Bedrock traffic drops to zero.

Level 2 — **harsher (if the flag does not work or is not in the
code)**:

```bash
# Remove the Bedrock invoke permission from the task IAM role inline
# policy. Without invoke rights the API immediately gets
# AccessDeniedException and returns 503.
aws iam delete-role-policy --role-name jsnotes-t2-ecs-task \
  --policy-name jsnotes-t2-bedrock-invoke

# Restore once the incident is closed: terraform apply (Terraform will
# bring the policy back).
```

This is a tougher path — it creates Terraform drift, but is
**guaranteed** to stop Bedrock traffic, even if no kill switch exists
in the code.

#### 9.4.3. Backend bug rollback (guard loop)

If the guard model is invoked in a loop because of a bug:

- Go to §6 Scenario B2: roll back to the previous `sha-<short>`.
- After the rollback — verify that guard invocations have returned to
  normal (CloudWatch metric).

#### 9.4.4. Reduce max_tokens / disable summary mode

If cost grows because of long responses (output tokens):

```bash
# Env vars (require a new TD revision, as in §9.4.2):
# LLM_MAX_OUTPUT_TOKENS=200       # instead of 1000
# LLM_SUMMARY_STRATEGY=compact-oldest  # instead of llm-based summarization
```

This is a soft mitigation — the Cloud agent still works, but cheaper.

### 9.5. Manual AWS Budget (deploy_user has no rights for the Budgets API)

Because Terraform does not manage AWS Budgets, we set them manually
via the Console — this is done by the instructor (AWS account owner):

1. AWS Console → Billing → Budgets → Create budget;
2. Type: Cost budget; Period: Monthly; Amount: $X (e.g. $30/month for
   the educational scope);
3. Email alerts: 80% / 100% thresholds → instructor's email + Marat's;
4. Filter: Service = Amazon Bedrock — a separate budget for the LLM;
5. Save a screenshot of the configuration in
   `_private/notes/sprint3/budgets-screenshot.md`.

This is **not part of the automated runbook**, but the runbook
references this budget as a detection mechanism (in place of the
missing alarm).

### 9.6. Verify

After any emergency action:

```bash
# 1. Bedrock invocations dropped to zero / the desired level
aws cloudwatch get-metric-statistics --namespace AWS/Bedrock \
  --metric-name Invocations --period 300 --statistics Sum \
  --start-time $(date -u -v -1H +%Y-%m-%dT%H:%M:%S) \
  --end-time $(date -u +%Y-%m-%dT%H:%M:%S) \
  --dimensions Name=ModelId,Value=eu.amazon.nova-lite-v1:0

# 2. UI graceful degradation: open jsnb.org, try AI-generate, make sure
#    the UI shows a clear message rather than a 5xx error
curl -X POST https://jsnb.org/api/v1/llm/generate \
  -H "Authorization: Bearer <test-jwt>" \
  -H "Content-Type: application/json" \
  -d '{"prompt":"test"}'
# With the kill switch on: 503 with body { "code": "LLM_CLOUD_AGENT_DISABLED" }

# 3. Cost Explorer shows the spend stopping (with a 24–48 hour lag
#    until visible in Cost Explorer — this is normal).
```

### 9.7. RTO

| Action                                | RTO   |
|---------------------------------------|-------|
| Block single user via a DB update     | 5–10 min |
| App-level kill switch (new TD)        | 10–15 min (register-task-definition + roll) |
| IAM policy revoke (hard kill)         | 5 min  |
| Reduce max_tokens                     | 10–15 min |
| Code rollback (guard loop fix)        | 15–25 min (see §6.7 B2) |

RPO = 0 (spend stops immediately, history is preserved in CloudTrail).

### 9.8. Follow-ups

- **`LLM_CLOUD_AGENT_ENABLED` flag (HIGH PRIORITY)** — confirmed
  2026-06-17 via live verification: the flag is **absent** in
  `api/app/` and absent from the active TD (revision 44). §9.4.2
  Level 1 in this runbook describes the target/future state. **In a
  real incident today — only Level 2 (IAM revoke) works.**
  Tracked: `larchanka-training/dmc-1-t2-notebook-api#74` (api + a
  sibling Terraform PR in `mono`).
- **User blocking mechanism (HIGH PRIORITY)** — a Liquibase migration
  adding `disabled_at TIMESTAMP NULL` to `users.users` + middleware in
  the API. Tracked: `larchanka-training/dmc-1-t2-notebook-api#73`.
  Without it §9.4.1 only works through destructive workarounds.
- **CloudWatch alarm on Bedrock daily cost** — via the Budgets API
  (after extending `deploy_user` rights).
- **Per-user token budget** in the DB — an atomic tokens-per-day
  counter, reset at midnight UTC. Protects against single-user abuse
  without a kill switch. Depends on the user-blocking mechanism above.
- **Exponential backoff** in guard-model retries — protects against
  the "retry loop" bug.
- **Anomaly detection** — if daily Bedrock cost > 3× rolling 7-day
  avg → alarm. Via CloudWatch Anomaly Detection.

---

## 10. Scenario F — Resend OTP outage

**Severity:** Sev-1 for F.outage / F.account_issue (new users
blocked) / Sev-2 for F.backend (a rollback can fix it) / Sev-3 for
F.user_specific. TTD: minutes — hours (depending on whether a user
complains immediately).

OTP emails do not arrive to users → they **cannot sign in** (auth
depends only on OTP, there are no passwords). Signed-in users with a
valid JWT keep working (including **offline-first WebLLM and
QuickJS** — see §5.0).

### 10.1. Context: single point of failure

OTP email delivery goes **only through Resend** (Marat's personal
account, see §1.2). There is no SES fallback. This is a **known
architectural gap**, recorded as Track 3 follow-up.

This means:

- Any Resend outage → 100% downtime of the auth flow;
- Any problem with Marat's Resend account (suspension, billing issue,
  account compromise) → the same effect;
- The verified sender (`noreply@jsnb.org`) is tied to Resend — if
  they remove the verification, we cannot send any email.

### 10.2. Identify

```bash
# 1. Resend status page
# https://status.resend.com/

# 2. API logs: send errors
aws logs filter-log-events --log-group-name /ecs/jsnotes-t2-api \
  --start-time $(date -u -v -30M +%s)000 \
  --filter-pattern '"resend" ?ERROR ?Exception ?"send_failed"' \
  | jq -r '.events[].message' | head -50

# 3. User reports: "the OTP is not arriving"
# Ask the user: which email? checked spam? request time?

# 4. Send a test email through the Resend API yourself
curl -X POST 'https://api.resend.com/emails' \
  -H "Authorization: Bearer $(aws secretsmanager get-secret-value \
       --secret-id jsnotes-t2-resend-api-key --query SecretString --output text)" \
  -H 'Content-Type: application/json' \
  -d '{
    "from": "noreply@jsnb.org",
    "to": "marat+runbook@gmail.com",
    "subject": "runbook test",
    "text": "if you see this, Resend works"
  }'
# 200 — Resend OK, problem in our backend.
# 4xx/5xx — Resend issue or API key issue.
# unset history after the test (contains the API key via --query).
```

### 10.3. Decision tree

| What Identify shows                              | Most likely | Actions |
|--------------------------------------------------|-------------|---------|
| Resend status page = down/degraded                | F.outage    | §10.4 — wait + communication |
| Resend OK, our backend `resend.send` exception    | Backend bug | §10.5 — code rollback or fix |
| Resend OK, our `from` rejected (verification)     | Sender unverified | §10.6 — re-verify sender |
| Resend OK, manual curl works, but user reports it does not | User-specific (spam/blocked) | §10.7 — user support |
| Resend API key invalid                             | Key rotation issue or leak (see §8.3.2) | §8 Scenario D |
| Resend account suspended                           | F.account_issue | §10.8 — escalate to Marat / Resend support |

### 10.4. F.outage — Resend service is down

Do not make hot moves, **wait** and **communicate**:

1. Message on the UI login page (via S3 + CloudFront, as in §7.5):
   ```bash
   aws s3 cp ./maintenance-otp.html s3://jsnotes-t2-frontend/maintenance-otp.html \
     --content-type 'text/html' --cache-control 'max-age=60'
   ```
   The UI should show "codes are temporarily not arriving, try later"
   when an OTP request is attempted. This is a **UI change** — the
   runbook cannot ship new UI on the fly; realistically —
   `maintenance-otp.html` as a static page + a CloudFront error pages
   redirect.
2. Twitter / email list: tell currently registered users — "you cannot
   sign in temporarily, we are aware". For those already signed in
   (with a valid JWT) the product still works.
3. Monitor Resend status every 15 minutes.
4. **Escalate to Track 3 follow-up:** if the outage > 4 hours — an
   argument for immediate SES fallback implementation.

### 10.5. F.backend — our backend is broken

Treat as Scenario B (API down):

- Go to §6 for diagnosis.
- If a new code change broke the send-path — roll back to the previous
  `sha-<short>` (§6.4).
- If an environment regression (e.g. `EMAIL_FROM` became a
  placeholder) — Scenario B1 (§6.3.3).

### 10.6. F.sender_unverified — sender verification was revoked

If Resend stopped accepting `noreply@jsnb.org`:

```text
1. Resend Dashboard → Domains → jsnb.org status check.
2. If the SPF/DKIM/MX records for jsnb.org changed or expired:
   - check the Cloudflare DNS audit log (since the last successful
     send) — who changed it?
   - if it was authentication theft: F.account_issue + Scenario D
     (Cloudflare token leak).
3. Re-add the SPF/DKIM records in Cloudflare:
   - the values come from Resend Dashboard → Domains → Configure.
4. Wait for DNS propagation (5–60 min).
5. In Resend Dashboard → Verify Domain.
6. Test send (§10.2 step 4).
```

### 10.7. F.user_specific — one user is not receiving

Not Sev-1, usually Sev-3:

- Check that the email is in the users table (`api/app/modules/users`).
- Check it is not in Resend bounce/complaint list (Dashboard →
  Suppressions).
- Check that the user's email provider is not blocking it (corporate
  Gmail with anti-phishing, Mail.ru with anti-spam).
- If it is in the bounce list — ask the user to check spam, ask them
  to whitelist `noreply@jsnb.org`, or alternatively to sign in with a
  different email.

### 10.8. F.account_issue — Marat's Resend account has issues

This is the most painful class: the Resend owner is Marat (§1.2).

**If Marat is available:**

1. Marat logs into the Resend Dashboard, identifies the cause
   (suspension / billing / verification issue).
2. If billing — pay.
3. If suspension — contact Resend support.
4. Recovery: minutes to days depending on the cause.

**If Marat is unavailable and Resend is blocked:**

- There is no way to quickly restore OTP delivery without an SES
  fallback.
- Escalation: the instructor decides on a contact channel with Marat.
- Workaround: spin up a **temporary Resend account on another person**
  + re-verify `jsnb.org` (≈ 60 minutes, requires DNS changes in
  Cloudflare → needs Marat for DNS).

This is **the main argument for an immediate SES fallback** — Track 3
can no longer be postponed.

### 10.9. Verify

After any recovery:

```bash
# 1. Test an OTP request via the API
curl -fsS -X POST https://jsnb.org/api/v1/auth/otp/request \
  -H 'Content-Type: application/json' \
  -d '{"email":"qa+runbook@jsnb.org"}'
# Expectation: 202 Accepted

# 2. Confirm the email actually arrived (qa+runbook@... — on-call's
#    test inbox)
# Optionally: full request + verify flow via the UI on a test account

# 3. Resend Dashboard → Logs → last 10 emails: successful deliveries,
#    none stuck in `queued`
```

### 10.10. RTO

| Sub-scenario               | RTO to stop-the-bleeding | RTO to full recovery |
|----------------------------|--------------------------|----------------------|
| F.outage (Resend down)     | 5 min (post a maintenance UI) | until Resend recovers (hours) |
| F.backend bug              | 15 min (rollback)               | 15–25 min                       |
| F.sender_unverified         | 10 min (re-verify)             | 5–60 min (DNS propagation)      |
| F.user_specific             | N/A                            | 1–2 days (user-side)            |
| F.account_issue (Marat available) | 10–30 min                  | depends on Resend                |
| F.account_issue (Marat unavailable) | hours — days (workaround Resend account) | until SES fallback ships |

### 10.11. Follow-up — Track 3 SES fallback (HIGH PRIORITY)

Post-Sprint #3 this is **the highest-priority** technical follow-up:

- Add **AWS SES** as a secondary email provider;
- Verify `noreply@jsnb.org` in SES (separate DNS setup);
- Backend logic: try Resend → on failure → try SES → only after both
  fail → log + 503;
- SES advantages:
  - tied to the AWS account (not a personal account),
  - managed via Terraform,
  - cheaper than Resend at scale;
- Drawback: SES is in sandbox mode by default — requires a production
  access request.

Without an SES fallback Scenario F has no good recovery path; the
runbook operates with workarounds.

### 10.12. Connection to other scenarios

- §8 Scenario D (RESEND_API_KEY leak) — a sub-case of F: key
  rotation = short OTP downtime.
- §11 Scenario G (handover) — the Resend account stays with Marat,
  so it does not "move" with AWS, which simplifies handover.

---

## 11. Scenario G — Sunset / ownership handover

**Severity:** N/A (a planned event, not an incident). TTD: known (the
date X is announced in advance).

This scenario is **not an emergency**, but planned. JS Notebook is an
educational project (see §1.1), and AWS funding is tied to the
instructor. After the course ends three outcomes are possible. This
section is the operational guide for each of them.

Unlike Scenarios A–F, there is no "time to recover" here; there is a
**date X** (the day funding ends) and preparation for it.

### 11.1. Three outcomes

The decision is taken **at least 30 days before X** between the
instructor and Marat:

| Outcome        | When to choose | What happens to the infra |
|----------------|---------------|---------------------------|
| **G.continue** | The instructor keeps paying | Nothing changes. This scenario does not activate. |
| **G.handover** | Marat (or another owner) takes over the payment | AWS account migration: either ownership transfer of the existing one, or migration to a new account |
| **G.shutdown** | Nobody pays | Graceful shutdown with archiving; the domain and Resend stay with Marat |

**Default assumption until the decision is taken:** G.continue. The
off-boarding checklist (§11.2) should be performed anyway "just in
case" — the artefacts will be useful in any scenario, including a
future restart.

### 11.2. Off-boarding checklist (30 days before X)

These steps are performed **regardless** of the chosen outcome. They
produce an archive from which the product can be restored under any
scenario, including a re-launch a year later.

#### 11.2.1. Confirm the date X

In writing (email / chat with a timestamp): "AWS funding ends from
YYYY-MM-DD". Without that all the following steps are guesses.

#### 11.2.2. Snapshot the Terraform state

```bash
# Snapshot of the current intended state — for a future migration
cd terraform/cloud
terraform init -reconfigure
terraform state pull > _private/archive/cloud-tfstate-$(date +%Y%m%d).json
terraform output -json > _private/archive/cloud-outputs-$(date +%Y%m%d).json

cd ../preview-cloud
terraform state pull > _private/archive/preview-tfstate-$(date +%Y%m%d).json
terraform output -json > _private/archive/preview-outputs-$(date +%Y%m%d).json
```

`_private/archive/` — a local folder with GPG encryption before
storing outside the repository. **DO NOT commit to git.**

#### 11.2.3. Backup RDS — manual snapshot with export

```bash
# Step 1. Manual snapshot of RDS
SNAPSHOT_ID="jsnotes-t2-db-archive-$(date +%Y%m%d)"
aws rds create-db-snapshot \
  --db-instance-identifier jsnotes-t2-db \
  --db-snapshot-identifier "$SNAPSHOT_ID"

aws rds wait db-snapshot-completed --db-snapshot-identifier "$SNAPSHOT_ID"

# Step 2. Export the snapshot to S3 as Parquet (for long-term storage
# outside AWS dependence)
EXPORT_TASK_ID="jsnotes-t2-export-$(date +%Y%m%d)"
aws rds start-export-task \
  --export-task-identifier "$EXPORT_TASK_ID" \
  --source-arn "arn:aws:rds:eu-north-1:867633231218:snapshot:${SNAPSHOT_ID}" \
  --s3-bucket-name jsnotes-t2-frontend \
  --iam-role-arn "arn:aws:iam::867633231218:role/rds-s3-export" \
  --kms-key-id "<KMS key id for encryption>"
# (The KMS key and IAM role for the export task are a separate setup; for
# the educational scope a pg_dump via ECS Exec is simpler — no new
# resources needed)

# Step 3. Alternative via pg_dump (without new infra)
aws ecs execute-command --cluster jsnotes-t2 \
  --task "$(aws ecs list-tasks --cluster jsnotes-t2 \
    --service-name jsnotes-t2-api --query 'taskArns[0]' --output text)" \
  --container api --interactive --command "/bin/sh"

# Inside the container:
# pg_dump "$DATABASE_URL" -Fc -f /tmp/jsnotes-archive.dump
# # Then copy /tmp/jsnotes-archive.dump outside via S3 or ECS Exec file
# # transfer (no sftp, but `aws s3 cp` works if the task role has IAM
# # permissions).
```

Save the dump locally (Marat's disk + a backup copy).

#### 11.2.4. Archive CloudWatch Logs for the last 30 days

```bash
# Create an export task for each important log group
for LG in /ecs/jsnotes-t2-api /ecs/jsnotes-t2-migrations; do
  TASK_ID="export-$(echo "$LG" | tr '/' '-')-$(date +%Y%m%d)"
  aws logs create-export-task \
    --log-group-name "$LG" \
    --from $(date -u -v -30d +%s)000 \
    --to $(date -u +%s)000 \
    --destination jsnotes-t2-frontend \
    --destination-prefix "log-archive/${TASK_ID}/"
done

# Check status
aws logs describe-export-tasks --status-code COMPLETED \
  --query 'exportTasks[].{Id:taskId,Group:logGroupName,Status:status.code}'
```

#### 11.2.5. Archive ECR images — last-good SHAs

```bash
# Save the last-good api and ui images locally (last 3 successful)
mkdir -p _private/archive/ecr

aws ecr get-login-password --region eu-north-1 | \
  docker login --username AWS --password-stdin \
  867633231218.dkr.ecr.eu-north-1.amazonaws.com

for TAG in api-sha-<latest3> ui-sha-<latest3> migrations-sha-<latest3>; do
  IMAGE="867633231218.dkr.ecr.eu-north-1.amazonaws.com/jsnotes-t2:${TAG}"
  docker pull "$IMAGE"
  docker save "$IMAGE" | gzip > "_private/archive/ecr/${TAG}.tar.gz"
done

# Alternative: push to a personal GHCR on the larchanka-training org
# (if you decide to keep deployable artefacts)
docker tag "$IMAGE" "ghcr.io/larchanka-training/jsnotes-archive:${TAG}"
docker push "ghcr.io/larchanka-training/jsnotes-archive:${TAG}"
```

#### 11.2.6. Archive Secrets Manager values

```bash
# CRITICAL: secret values must not be lost, but cannot be stored as
# plaintext. Steps:

# Step 1. Retrieve all values locally (via ssh tunnel or ECS Exec, so
# nothing lands in the shell history of Marat's machine):
SECRETS="jsnotes-t2-jwt-secret jsnotes-t2-otp-hash-secret \
         jsnotes-t2-database-url jsnotes-t2-db-migration \
         jsnotes-t2-resend-api-key jsnotes-t2-email-from"

for S in $SECRETS; do
  V=$(aws secretsmanager get-secret-value --secret-id "$S" \
    --query SecretString --output text)
  # GPG encrypt immediately, do not write plaintext to disk
  echo "$V" | gpg --encrypt --recipient marat@... \
    > "_private/archive/secrets/${S}.gpg"
  unset V
done

# Step 2. Clear shell history
history -c
unset HISTFILE
```

Storage of `_private/archive/secrets/*.gpg`:

- GPG-encrypted with Marat's private key;
- two copies: local disk + offline backup (1Password / encrypted USB);
- **do not commit** even encrypted to git (paranoid level — encryption
  algorithms become outdated over 10 years).

#### 11.2.7. Archive the Cloudflare DNS config

```bash
# Via the Cloudflare API export the current DNS zone:
# Dashboard → DNS → Export → BIND zone file
# Save as _private/archive/cloudflare-jsnb.org-zone-YYYYMMDD.txt
```

This is needed for:

- fast restoration of DNS records after a future restart;
- comparison of "before / after" if changes happened unintentionally
  (see §8.3.7).

#### 11.2.8. Final-state documentation

Snapshot:

- `git rev-parse HEAD` of all three repos (mono/api/ui) at the moment
  of X;
- AWS Console screenshots: ECS services, RDS, CloudFront, Secrets;
- list of all CloudWatch metrics for the last 30 days (if a future
  restart with the same performance baseline is planned);
- the final version of `_private/notes/sprint3/infra-baseline.md`
  with the date stamp.

### 11.3. G.handover — ownership transfer

After §11.2 we have a full archive. Handover is the transfer of the
**live infra** to a new owner.

#### 11.3.1. Option A — AWS Organization invite (if the new owner already has an AWS account)

**The simplest path:** keep the resources in the current account
`867633231218`, add the new owner via AWS Organizations.

```text
1. Instructor: AWS Console → AWS Organizations → Invite account
   → new owner's email → Send invite.
2. New owner accepts the invite via their AWS account.
3. Instructor moves billing to the new owner (Consolidated billing).
4. Instructor hands over root credentials or creates an IAM admin user
   for the new owner (the second is preferable — do not transfer root
   credentials).
5. Marat updates GitHub Secrets (AWS_ACCESS_KEY_ID/SECRET) to the new
   IAM admin keys.
6. Smoke (§2.3) → confirms the pipeline works under the new rights.
```

**Advantages:** minimal migration, ARNs do not change.

**Constraints for an RF resident (Marat):** AWS billing for RF
residents is restricted by sanctions. **Realistically:** a new AWS
account via AWS Org cannot be registered with RF billing. So:

- if the new owner is Marat and he is an RF resident → Option A does
  not work directly;
- alternative: use an **AWS reseller via a third country** (legit AWS
  partners exist in Kazakhstan, Turkey, Serbia);
- alternative 2: a registered legal entity **outside RF** — if Marat
  has / can register one in EU.

Without a clean resolution of the sanctions constraints → switch to
Option B or G.shutdown.

#### 11.3.2. Option B — Migration to a new AWS account

If Option A is not possible (sanctions, or the instructor wants to
fully detach from the infra):

```text
1. New owner registers a new AWS account (subject to §11.3.1
   constraints).
2. New owner requests Bedrock model access (Nova Lite/Micro) — this
   is not an automatic grant, wait for AWS approval (minutes to hours
   for EU accounts).
3. New owner creates an IAM admin user, hands credentials to Marat.
4. Marat in the new account:
   a. Run `infra-bootstrap.yml` → create the Terraform state bucket;
   b. Update GitHub Secrets (AWS_ACCESS_KEY_ID/SECRET, ECR registry
      ARN in `terraform/modules/backend/variables.tf`);
   c. Run `infra-cloud.yml` apply → fresh infra in the new account.
5. Data recovery:
   a. Import RDS snapshot: `aws rds restore-db-instance-from-db-snapshot`
      from the local archive (if the snapshot was copied cross-account
      before X) OR pg_restore via ECS Exec from the local dump;
   b. Restore secrets from the GPG archive (§11.2.6) → put-secret-value
      into the new Secrets Manager containers;
   c. ECR push images from local tar.gz (or re-build from source).
6. Update Cloudflare:
   a. The CloudFront domain in the new account is different
      (`d<new>...cloudfront.net`);
   b. Update aliases `jsnb.org`/`www.jsnb.org` to the new CloudFront
      domain;
   c. Re-issue ACM cert in `us-east-1` (DNS validation via Cloudflare);
   d. Update the FRONTEND_ACM_CERTIFICATE_ARN GitHub variable.
7. Smoke (§2.3) → confirm the full stack works.
8. After 24 hours of observation — the instructor closes the old AWS
   account: `terraform destroy` (after disabling RDS deletion_protection).
```

**RTO for migration:** 2–7 days (depends on Bedrock model access
approval, DNS propagation, and how quickly Marat performs the steps).

**RPO:** up to the time of the last pg_dump before X (hours — days).

#### 11.3.3. Post-handover verification

At a minimum:

- jsnb.org resolves and returns 200 (UI + `/api/v1/health`);
- OTP request → the user receives an email;
- the Cloud agent works (Bedrock invoke OK);
- `deploy-cloud.yml workflow_dispatch` successfully deploys a test PR;
- billing alerts are configured for the new owner.

### 11.4. G.shutdown — Graceful shutdown

If you decide not to continue. This is a **destructive** sequence,
do not perform without confirmation from Marat and the instructor.

#### 11.4.1. Pre-shutdown (7 days before actual shutdown)

```text
1. User notification: email to all registered users + UI banner
   ("the service is being shut down on DD-MM-YYYY, please download
   your notebooks").
2. Self-export for users: confirm the UI has an export button for
   notebooks (JSON / ZIP). As of 2026-06-17 it is **absent**.
   Tracked: `larchanka-training/dmc-1-t2-notebook-ui#82`. This is a
   blocker for shutdown — must be closed by date X.
3. Confirm the §11.2 archive has been made.
```

#### 11.4.2. Shutdown sequence

In strict order:

```bash
# Step 1. ECS desired_count → 0 (stop the API)
aws ecs update-service --cluster jsnotes-t2 --service jsnotes-t2-api \
  --desired-count 0
aws ecs wait services-stable --cluster jsnotes-t2 --services jsnotes-t2-api

# Step 2. User-facing maintenance page (via S3 + CloudFront)
aws s3 cp ./shutdown.html s3://jsnotes-t2-frontend/index.html \
  --content-type 'text/html' --cache-control 'max-age=3600'
aws cloudfront create-invalidation --distribution-id E29EW3R1X0PB5W --paths '/*'

# Step 3. (Optional) CloudFront disable — the user will see the
# CloudFront default error
aws cloudfront get-distribution-config --id E29EW3R1X0PB5W \
  --output json > /tmp/cf-config.json
# Edit Enabled: false, then update
# aws cloudfront update-distribution --id E29EW3R1X0PB5W \
#   --distribution-config file:///tmp/cf-config.json --if-match <ETag>

# Step 4. Final RDS snapshot BEFORE destroy
FINAL_SNAPSHOT="jsnotes-t2-db-final-$(date +%Y%m%d)"
aws rds create-db-snapshot --db-instance-identifier jsnotes-t2-db \
  --db-snapshot-identifier "$FINAL_SNAPSHOT"
aws rds wait db-snapshot-completed --db-snapshot-identifier "$FINAL_SNAPSHOT"

# Step 5. ECR cleanup (optional — leave tagged images in the archive)
# aws ecr batch-delete-image --repository-name jsnotes-t2 ...

# Step 6. Remove deletion_protection from RDS (Terraform var or direct modify)
aws rds modify-db-instance --db-instance-identifier jsnotes-t2-db \
  --no-deletion-protection --apply-immediately

# Step 7. Terraform destroy (requires confirmation)
cd terraform/cloud
terraform destroy
# Terraform asks "Do you really want to destroy?" → yes

cd ../preview-cloud
terraform destroy
```

#### 11.4.3. Post-shutdown — what stays with Marat

- The `jsnb.org` domain (Cloudflare) — can be switched to a static
  "memorial page" or sold;
- the Resend account (irrelevant without the service, but can stay on
  the free tier);
- GitHub repos (mono/api/ui) — remain, available read-only to anyone;
- the archive (§11.2): tfstate, RDS dump, secrets.gpg, ECR images,
  Cloudflare zone, CloudWatch logs.

This is enough for a **future restart**, if anyone wants to bring the
project back later.

### 11.5. G.future_restart — restoration from the archive

Suppose 6 months later it is decided to bring the product back. We
have everything from §11.2.

```text
1. A new AWS account (or an existing one) — set up via §11.3.1/B.
2. Request Bedrock model access (Nova Lite/Micro) → wait for approval.
3. Update the local monorepo clone to the last commit at the moment
   of X (see §11.2.8).
4. `terraform/cloud/variables.tf`: update `aws_region` if different,
   `project` prefix if it changes.
5. `infra-bootstrap.yml` → state bucket.
6. `infra-cloud.yml` apply → create the infra (empty).
7. Data restoration:
   a. `aws rds restore-db-instance-from-db-snapshot` from the local
      snapshot (if copied) OR pg_restore via ECS Exec from the local
      dump after the first API deploy.
   b. Restore secrets: `gpg --decrypt secret.gpg | aws secretsmanager
      put-secret-value --secret-id ... --secret-string`.
   c. ECR push images from the local archive or re-build from source.
8. Update Cloudflare DNS → the new CloudFront domain.
9. Re-issue ACM cert in `us-east-1`.
10. Update the FRONTEND_ACM_CERTIFICATE_ARN GitHub variable.
11. Smoke (§2.3).
12. Publish a "Welcome back" UI banner or do a silent restart.
```

**RTO for a cold restart:** 1–3 days (accounting for Bedrock approval).

**What is NOT restored:**

- **CloudFront distribution ID** — new. All logs / metrics — from zero.
- **CloudWatch logs** — for the shutdown period they do not exist; for
  the period before shutdown — from the archive (if exported).
- **Bedrock approval status** — must be requested again on the new
  account.
- **CloudFront `*.cloudfront.net` domain** — new, not controlled by
  us. The Cloudflare aliases must point to the new one.
- **User sessions** — all invalidated (a new `JWT_SECRET` or one
  restored from the archive — both are valid options).

### 11.6. Follow-ups (for a smooth handover)

If there is time before date X:

- **Cross-account RDS snapshot copy** — set up a regular snapshot
  copy to **Marat's personal AWS account** (or another backup account).
  Then the G.shutdown scenario stops depending on the final snapshot
  at the moment of X.
- **GitHub Container Registry archive** — set up a parallel push from
  ECR to GHCR for all release tags. Then the ECR images archive is
  not needed locally.
- **Documented domain transfer procedure** — if Marat decides to
  hand over jsnb.org to a future owner, the procedure should be ready.
- **Resend → SES migration** — in parallel with any handover
  scenario: unhook OTP delivery from the personal Resend account.
  Track 3 is HIGH PRIORITY in any case.

### 11.7. Honest gaps

- **Cross-account RDS snapshot copy** — not configured today. This
  means the archive via snapshot only works until X; after X the
  snapshot will stay in the old account until that account is closed.
- **`terraform destroy` for the preview environment** — not tested on
  a real destroy (deletion_protection on resources other than RDS may
  surface).
- **Bedrock Geo profile in a new account** — granting an inference
  profile in a new account may require a manual policy attach. The
  exact procedure is not documented.
- **Cloudflare API token** for the new owner — Marat remains the
  domain owner, so the token is not transferred; but if the domain is
  **also** transferred, a full domain transfer playbook is needed
  (out of scope for this runbook).

---

## 12. Universal verification checklist

Run after **any** recovery (scenarios A–F) and after G.future_restart.
If all 4 sections are green, the recovery is considered successful and
the incident can be closed.

### 12.1. Smoke (§2.3 recap)

```bash
PROD_URL="https://jsnb.org"
ALB_DNS=$(aws elbv2 describe-load-balancers --names jsnotes-t2-alb \
  --query 'LoadBalancers[0].DNSName' --output text)

# 1. UI loads
curl -fsS -o /dev/null -w "UI:        %{http_code} %{size_download}b %{time_total}s\n" \
  "${PROD_URL}/"

# 2. API health via CloudFront
curl -fsS -w "API CF:    %{http_code} %{time_total}s\n" \
  "${PROD_URL}/api/v1/health"

# 3. ALB direct (bypassing CloudFront)
curl -fsS -w "API ALB:   %{http_code} %{time_total}s\n" \
  "http://${ALB_DNS}/api/v1/health"

# 4. OTP request (auth chain works)
curl -fsS -w "OTP req:   %{http_code}\n" -X POST \
  "${PROD_URL}/api/v1/auth/otp/request" \
  -H 'Content-Type: application/json' \
  -d '{"email":"qa+runbook@jsnb.org"}'
```

**Expected:** all 4 = 200 (UI/health) or 202 (OTP), or 429 for OTP
(rate-limit — also OK).

### 12.2. ECS service stable

```bash
aws ecs describe-services --cluster jsnotes-t2 --services jsnotes-t2-api \
  --query 'services[0].{TD:taskDefinition,Desired:desiredCount,Running:runningCount,Pending:pendingCount,Rollout:deployments[0].rolloutState,RolloutReason:deployments[0].rolloutStateReason}' \
  --output table
```

**Expected:**

- `Running == Desired`;
- `Pending == 0`;
- `Rollout = COMPLETED`;
- `RolloutReason` empty or contains "ECS deployment ... completed".

### 12.3. RDS available

```bash
aws rds describe-db-instances --db-instance-identifier jsnotes-t2-db \
  --query 'DBInstances[0].{Status:DBInstanceStatus,Storage:AllocatedStorage,Pending:PendingModifiedValues}' \
  --output table
```

**Expected:** `Status = available`, `PendingModifiedValues` empty.

### 12.4. Fresh logs without errors

```bash
aws logs tail /ecs/jsnotes-t2-api --since 10m \
  --filter-pattern '?ERROR ?CRITICAL ?Exception ?Traceback' | head -50
```

**Expected:** empty (or only known-noise patterns, documented
separately).

### 12.5. End-to-end test (optional for Sev-1)

After Sev-1 — a full test flow on a test account:

1. Open `https://jsnb.org/`.
2. Sign in: request OTP → check the inbox → enter the code.
3. Create a notebook, add a markdown + code cell.
4. Run the code cell, verify the output.
5. AI-generate in a new cell.
6. Sign out → sign in again.

Any failure in steps 1–6 — **recovery is incomplete**, re-open the
sub-scenario.

---

## 13. Postmortem template

Filled in after any Sev-1 / Sev-2 incident. Saved to
`_private/summaries_memory/incident_<YYYY-MM-DD>_<short-slug>.md`.

A ready example of the format —
`_private/summaries_memory/sprint2_follow-up/deploy_cloud_resend_secret_rollback_14_06_2026.md`.

### Template

```markdown
# Incident postmortem — <YYYY-MM-DD> — <one-line title>

## Severity and impact

- **Severity:** Sev-1 / Sev-2 / Sev-3
- **Started:** YYYY-MM-DDTHH:MM:SSZ (when the symptoms appeared)
- **Detected:** YYYY-MM-DDTHH:MM:SSZ (when on-call learned)
- **Mitigated:** YYYY-MM-DDTHH:MM:SSZ (when stop-the-bleeding was done)
- **Resolved:** YYYY-MM-DDTHH:MM:SSZ (when smoke was green)
- **Time-to-detect:** Detected − Started
- **Time-to-mitigate:** Mitigated − Detected
- **Time-to-resolve:** Resolved − Detected
- **User impact:** N users, M minutes of downtime, which features were down

## Trigger

What exactly happened. One or two paragraphs.

Example:
> After the merge of monorepo PR `larchanka-training/dmc-1-t2-notebook-mono#118`
> (a submodule pointer bump to api with OTP email delivery), ECS deploy
> deployed a task definition with mandatory production validation for
> `RESEND_API_KEY` and `EMAIL_FROM`.
> These secret values had not been initialized in Secrets Manager.
> ECS startup failed the health check → circuit breaker rolled back
> the deployment.

## Root cause

Why this happened. Usually a chain of causes:

1. Immediate cause: ...
2. Contributing factor: ...
3. Root cause (5 whys): ...

Example:
> 1. Immediate: ECS task fails on startup → validator exception.
> 2. Contributing: `infra-cloud.yml` creates the secret container but
>    does not set the value automatically.
> 3. Root: the API code received production startup validation in the
>    upstream api PR; monorepo PR
>    `larchanka-training/dmc-1-t2-notebook-mono#118` bumped the
>    submodule pointer, but the bootstrap process for secret values in
>    Terraform/CI was not updated at the same time. **The api ↔ infra
>    contract changed without a coordinated PR in monorepo.**

## Detection

How we learned. Time from Trigger to Detection (important — this is
an observability quality metric).

If detection was reactive (a user complaint, accidentally noticing a
red deploy) — this is **proof of an improvement needed in
observability** (see runbook §3.2).

## Timeline (UTC)

```
HH:MM  Trigger event (merge / deploy / ...)
HH:MM  Detection (which channel)
HH:MM  First responder ack ($whoami)
HH:MM  Diagnose started: ...
HH:MM  Hypothesis #1: ... — ruled out by ...
HH:MM  Hypothesis #2: ... — confirmed by ...
HH:MM  Mitigation action #1: ...
HH:MM  Mitigation action #2: ...
HH:MM  Smoke green
HH:MM  Communication: "resolved" to users
```

## Recovery actions

What we did, in order. With references to runbook scenarios.

Example:
> 1. §6.3.1 Freeze pipeline (`gh api ... /disable`).
> 2. §6.3.3 `aws secretsmanager put-secret-value` for RESEND_API_KEY and EMAIL_FROM.
> 3. `aws ecs update-service --force-new-deployment`.
> 4. `aws ecs wait services-stable`.
> 5. §12.1 smoke verification.
> 6. §6.3.5 Unfreeze pipeline.

## What worked well

- What in the system / pipeline / runbook design saved us from the
  worst outcome.
- If the runbook had not existed, what would have been worse / slower.

Example:
> - ECS circuit breaker automatically rolled back the deployment →
>   user-facing impact was limited to new users (existing sessions kept
>   working).
> - Immutable `sha-<short>` tags — we knew exactly which revision to
>   roll back to.

## What did NOT work

- What should have prevented the incident and did not.
- What slowed down detection / mitigation.

Example:
> - Detection was reactive — we learned from a user complaint in chat,
>   not from an alarm.
> - There was no pre-deploy check for secret values.
> - Review of monorepo PR `larchanka-training/dmc-1-t2-notebook-mono#118`
>   did not catch the missing parallel infra-cloud.yml update.

## Action items

Concrete, owned, with deadlines.

| # | Action | Owner | Due | Priority |
|---|--------|-------|-----|----------|
| 1 | Add pre-deploy secret presence check to `infra-cloud.yml` | DevOps | YYYY-MM-DD | P1 |
| 2 | CloudWatch alarm on `ECS-ServiceDeploymentFailed` event | DevOps | YYYY-MM-DD | P1 |
| 3 | PR review checklist: "paired api ↔ infra changes" | Tech Lead | YYYY-MM-DD | P2 |
| 4 | Documented inventory of required secrets for prod startup | DevOps | YYYY-MM-DD | P2 |

## Links

- Trigger PR: <link>
- Recovery PR (if any): <link>
- Slack/chat thread: <link or N/A>
- CloudWatch logs links: <link or N/A>
- This runbook scenario: §6 B1
```

---

## 14. Appendix A — AWS CLI shorthand

Ready-to-copy command set. They all use canonical names from §2 /
`_private/notes/sprint3/infra-baseline.md`.

### 14.1. Environment setup

```bash
export AWS_REGION=eu-north-1
export ECS_CLUSTER=jsnotes-t2
export ECS_SERVICE=jsnotes-t2-api
export TASK_FAMILY=jsnotes-t2-api
export MIG_TASK_FAMILY=jsnotes-t2-migrations
export RDS_ID=jsnotes-t2-db
export ALB_NAME=jsnotes-t2-alb
export TG_NAME=jsnotes-t2-api-tg
export FRONTEND_BUCKET=jsnotes-t2-frontend
export CLOUDFRONT_DIST_ID=E29EW3R1X0PB5W   # confirm via list-distributions
export ECR_REGISTRY=867633231218.dkr.ecr.eu-north-1.amazonaws.com
export ECR_REPO=jsnotes-t2
export PROD_URL=https://jsnb.org
export LOG_GROUP_API=/ecs/jsnotes-t2-api
export LOG_GROUP_MIG=/ecs/jsnotes-t2-migrations
```

### 14.2. ECS

```bash
# Service state
aws ecs describe-services --cluster $ECS_CLUSTER --services $ECS_SERVICE \
  --query 'services[0].{TD:taskDefinition,Desired:desiredCount,Running:runningCount,Pending:pendingCount,Rollout:deployments[0].rolloutState}' --output table

# Service events (last 10)
aws ecs describe-services --cluster $ECS_CLUSTER --services $ECS_SERVICE \
  --query 'services[0].events[0:10].[createdAt,message]' --output table

# Active TD details
aws ecs describe-task-definition --task-definition $(aws ecs describe-services \
  --cluster $ECS_CLUSTER --services $ECS_SERVICE \
  --query 'services[0].taskDefinition' --output text) \
  --query 'taskDefinition.containerDefinitions[0].{Image:image,Env:environment,Secrets:secrets[].name}' --output json

# List recent TD revisions
aws ecs list-task-definitions --family-prefix $TASK_FAMILY --sort DESC --max-items 10

# Force new deployment (after a secret value change)
aws ecs update-service --cluster $ECS_CLUSTER --service $ECS_SERVICE --force-new-deployment

# Rollback to a specific TD
aws ecs update-service --cluster $ECS_CLUSTER --service $ECS_SERVICE --task-definition <TD_ARN>

# Wait stable
aws ecs wait services-stable --cluster $ECS_CLUSTER --services $ECS_SERVICE

# Stopped tasks with reason
aws ecs list-tasks --cluster $ECS_CLUSTER --service-name $ECS_SERVICE --desired-status STOPPED \
  --query 'taskArns' --output text | \
  xargs -n1 -I{} aws ecs describe-tasks --cluster $ECS_CLUSTER --tasks {} \
    --query 'tasks[].{Stopped:stoppedReason,Code:stopCode,Exit:containers[0].exitCode}' --output json

# ECS Exec into a running task (debug shell)
TASK=$(aws ecs list-tasks --cluster $ECS_CLUSTER --service-name $ECS_SERVICE \
  --desired-status RUNNING --query 'taskArns[0]' --output text)
aws ecs execute-command --cluster $ECS_CLUSTER --task "$TASK" \
  --container api --interactive --command "/bin/sh"
```

### 14.3. RDS

```bash
# Instance state
aws rds describe-db-instances --db-instance-identifier $RDS_ID \
  --query 'DBInstances[0].{Status:DBInstanceStatus,Endpoint:Endpoint.Address,Engine:Engine,LatestRestorableTime:LatestRestorableTime,Storage:AllocatedStorage,MultiAZ:MultiAZ}' --output table

# Events (last 24h)
aws rds describe-events --source-identifier $RDS_ID --source-type db-instance --duration 1440 \
  --query 'Events[].[Date,Message]' --output table

# Manual snapshot
aws rds create-db-snapshot --db-instance-identifier $RDS_ID \
  --db-snapshot-identifier "${RDS_ID}-manual-$(date +%Y%m%d%H%M)"

# List snapshots
aws rds describe-db-snapshots --db-instance-identifier $RDS_ID \
  --query 'sort_by(DBSnapshots, &SnapshotCreateTime)[].{Id:DBSnapshotIdentifier,Type:SnapshotType,Created:SnapshotCreateTime,Status:Status}' --output table

# PITR (see §5.4.1 / §5.4.2 for the full procedure)
aws rds restore-db-instance-to-point-in-time \
  --source-db-instance-identifier $RDS_ID \
  --target-db-instance-identifier "${RDS_ID}-restore-$(date +%Y%m%d%H%M)" \
  --restore-time "<YYYY-MM-DDTHH:MM:SSZ>" \
  --db-subnet-group-name jsnotes-t2-db-subnet-group \
  --no-multi-az --no-publicly-accessible \
  --db-instance-class db.t3.micro --storage-type gp3

# Modify master password (§8.3.5)
aws rds modify-db-instance --db-instance-identifier $RDS_ID \
  --master-user-password "<NEW_PASS>" --apply-immediately
```

### 14.4. Secrets Manager

```bash
# List project secrets
aws secretsmanager list-secrets --filters Key=name,Values=jsnotes-t2 \
  --query 'SecretList[].{Name:Name,ARN:ARN,LastChanged:LastChangedDate}' --output table

# Describe (without reading the value!)
aws secretsmanager describe-secret --secret-id <NAME> \
  --query '{LastChanged:LastChangedDate,Versions:VersionIdsToStages}' --output json

# Put new value
aws secretsmanager put-secret-value --secret-id <NAME> --secret-string "<VALUE>"

# Version-stage rollback (§5.4.5 / §8.3)
aws secretsmanager update-secret-version-stage --secret-id <NAME> \
  --version-stage AWSCURRENT \
  --move-to-version-id <PREVIOUS_VID> --remove-from-version-id <CURRENT_VID>
```

### 14.5. CloudFront / S3

```bash
# Find a distribution by alias
aws cloudfront list-distributions \
  --query "DistributionList.Items[?contains(Aliases.Items || \`[]\`, 'jsnb.org')].Id" --output text

# Invalidation
aws cloudfront create-invalidation --distribution-id $CLOUDFRONT_DIST_ID --paths "/*"

# S3 sync UI (deploy)
aws s3 sync ./dist "s3://$FRONTEND_BUCKET" --delete
```

### 14.6. ALB

```bash
# DNS name
ALB_DNS=$(aws elbv2 describe-load-balancers --names $ALB_NAME \
  --query 'LoadBalancers[0].DNSName' --output text)
echo "$ALB_DNS"

# Target health
TG_ARN=$(aws elbv2 describe-target-groups --names $TG_NAME \
  --query 'TargetGroups[0].TargetGroupArn' --output text)
aws elbv2 describe-target-health --target-group-arn "$TG_ARN" \
  --query 'TargetHealthDescriptions[].{Target:Target.Id,State:TargetHealth.State,Reason:TargetHealth.Reason,Desc:TargetHealth.Description}' --output table
```

### 14.7. CloudWatch Logs

```bash
# Tail recent
aws logs tail $LOG_GROUP_API --since 30m

# Tail with a filter
aws logs tail $LOG_GROUP_API --since 1h \
  --filter-pattern '?ERROR ?Exception ?Traceback'

# Insights query (async)
QID=$(aws logs start-query --log-group-name $LOG_GROUP_API \
  --start-time $(date -u -v -1H +%s) --end-time $(date -u +%s) \
  --query-string '<QUERY>' --query queryId --output text)
sleep 5
aws logs get-query-results --query-id "$QID"
```

### 14.8. ECR

```bash
# Login
aws ecr get-login-password | docker login --username AWS --password-stdin $ECR_REGISTRY

# Last 10 api images
aws ecr describe-images --repository-name $ECR_REPO --filter tagStatus=TAGGED \
  --query 'sort_by(imageDetails, &imagePushedAt)[-10:].{Tags:imageTags,Pushed:imagePushedAt}' --output table
```

---

## 15. Appendix B — CloudWatch Logs Insights queries

Saved queries for typical incident diagnostics. Run any of them as:

```bash
aws logs start-query --log-group-name <GROUP> \
  --start-time $(date -u -v -1H +%s) --end-time $(date -u +%s) \
  --query-string '<QUERY-from-this-appendix>'
```

### 15.1. API startup / boot errors (for B1 config regression)

```text
filter @message like /(validation error|configuration|missing required|secret|password authentication)/
  | sort @timestamp desc
  | limit 100
```

### 15.2. 5xx burst over the last hour (for B2)

```text
filter @message like /HTTP\/1\.1" 5\d{2}/
  | parse @message /(?<status>\d{3})/
  | stats count() as cnt by bin(5m), status
  | sort @timestamp asc
```

### 15.3. LLM requests per user (for E single-user abuse)

```text
filter event = "llm.requested"
  | stats count() as requests, sum(prompt_tokens + completion_tokens) as total_tokens
        by user_id
  | sort total_tokens desc
  | limit 20
```

### 15.4. Auth failures pattern (for D security audit)

```text
filter event = "auth.failed" or @message like /(unauthorized|invalid_token|too_many_otp_attempts)/
  | stats count() as failures by bin(15m), source_ip
  | sort failures desc
  | limit 50
```

### 15.5. Slow LLM calls (for performance / E retry loop)

```text
filter event = "llm.requested" and duration_ms > 5000
  | stats avg(duration_ms) as avg_ms, max(duration_ms) as max_ms, count() as cnt by bin(5m), model_id
  | sort @timestamp asc
```

### 15.6. Migration task results (for A4)

```text
fields @timestamp, @message
  | filter @message like /(SUCCESSFUL|EXECUTED|FAILED|ROLLBACK|Liquibase command 'update' was executed)/
  | sort @timestamp desc
  | limit 50
```

Run against `$LOG_GROUP_MIG`.

### 15.7. Secret-related startup failures (catch-all for B1)

```text
filter @message like /(NoCredentialsError|ResourceInitializationError|AccessDenied|GetSecretValue)/
  | stats count() as cnt by bin(15m), @message
  | sort cnt desc
  | limit 20
```

### 15.8. Rate-limit hits (for E + D recovery verification)

```text
filter @message like /(too_many_otp|429|rate_limit)/
  | stats count() as cnt by bin(5m), @message
  | sort @timestamp asc
```

---

## 16. Appendix C — App-level kill switches

A single block with all available kill switches. Use them in cases of
mass abuse / cost spike / known-bad code in production.

### 16.1. LLM Cloud-agent off

**Level 1 — env var (target/future, does NOT work today):**

> ⚠ Confirmed 2026-06-17: the `LLM_CLOUD_AGENT_ENABLED` env flag is
> absent from the code and from the active TD. This level is for
> future implementation. In a real incident today use **Level 2**
> below.

```bash
# Requires the API code to check LLM_CLOUD_AGENT_ENABLED. Currently it
# does NOT — a PR in api/ and terraform/ is needed (see §9.8 HIGH
# PRIORITY).

ACTIVE_TD=$(aws ecs describe-services --cluster $ECS_CLUSTER --services $ECS_SERVICE \
  --query 'services[0].taskDefinition' --output text)

NEW_TD_JSON=$(aws ecs describe-task-definition --task-definition "$ACTIVE_TD" \
  --query 'taskDefinition' --output json | \
  jq '.containerDefinitions[0].environment += [{"name":"LLM_CLOUD_AGENT_ENABLED","value":"false"}]
      | del(.taskDefinitionArn, .revision, .status, .requiresAttributes, .compatibilities, .registeredAt, .registeredBy)')

KILL_TD=$(echo "$NEW_TD_JSON" | aws ecs register-task-definition --cli-input-json file:///dev/stdin \
  --query 'taskDefinition.taskDefinitionArn' --output text)

aws ecs update-service --cluster $ECS_CLUSTER --service $ECS_SERVICE \
  --task-definition "$KILL_TD" --force-new-deployment
```

Rollback — apply Terraform (it will restore env without
LLM_CLOUD_AGENT_ENABLED).

**Level 2 — IAM revoke (hard kill, guaranteed):**

```bash
# Remove the Bedrock invoke policy
aws iam delete-role-policy --role-name jsnotes-t2-ecs-task \
  --policy-name jsnotes-t2-bedrock-invoke

aws ecs update-service --cluster $ECS_CLUSTER --service $ECS_SERVICE --force-new-deployment
```

Rollback — `terraform apply` (will restore the policy from
`terraform/modules/backend/bedrock.tf`).

### 16.2. ECS desired_count → 0 (full API shutdown)

```bash
# Use only for G.shutdown or an extreme Sev-1.
# Fully stops the API: the UI still works (CloudFront/S3), but any
# /api/v1/* call → 502.

aws ecs update-service --cluster $ECS_CLUSTER --service $ECS_SERVICE --desired-count 0
aws ecs wait services-stable --cluster $ECS_CLUSTER --services $ECS_SERVICE

# Restore:
aws ecs update-service --cluster $ECS_CLUSTER --service $ECS_SERVICE --desired-count 1
aws ecs wait services-stable --cluster $ECS_CLUSTER --services $ECS_SERVICE
```

### 16.3. CloudFront origin disable / maintenance page

```bash
# Replace the S3 index.html with a maintenance page
aws s3 cp ./maintenance.html s3://$FRONTEND_BUCKET/index.html \
  --content-type 'text/html' --cache-control 'max-age=60'
aws cloudfront create-invalidation --distribution-id $CLOUDFRONT_DIST_ID --paths '/' '/index.html'

# Restore — re-deploy the UI via `aws s3 sync` (see §14.5)
```

### 16.4. Block single user (for E.single-user abuse)

> ⚠ **Architectural gap (2026-06-17):** there is no `disabled_at`
> column in `users.users` (see `api/app/modules/auth/models/user.py`).
> Per-user blocking in isolation is **not available** without a code
> change. Tracked: `larchanka-training/dmc-1-t2-notebook-api#73`.
> Details — §9.4.1.

Available workarounds:

- §9.4.2 — Cloud-agent kill switch (if abuse is specifically on the
  LLM path; affects all Cloud-agent users uniformly);
- §8.3.3 — Rotate JWT_SECRET (forces re-login for all users; then a
  bot won't pass OTP — if it really is a bot);
- Hard delete the user row (irreversibly deletes user + notebooks via
  CASCADE; only for a confirmed bot):

```bash
TASK=$(aws ecs list-tasks --cluster $ECS_CLUSTER --service-name $ECS_SERVICE \
  --desired-status RUNNING --query 'taskArns[0]' --output text)
aws ecs execute-command --cluster $ECS_CLUSTER --task "$TASK" \
  --container api --interactive --command "/bin/sh"
# psql "$DATABASE_URL" -c "DELETE FROM users.users WHERE id = '<USER_UUID>';"
```

Follow-up for a proper implementation — §9.8: migration + middleware.

### 16.5. Freeze CI/CD pipeline

```bash
# Disable the deploy pipeline (see §6.3.1)
gh api -X PUT \
  /repos/larchanka-training/dmc-1-t2-notebook-mono/actions/workflows/deploy-cloud.yml/disable

# Restore
gh api -X PUT \
  /repos/larchanka-training/dmc-1-t2-notebook-mono/actions/workflows/deploy-cloud.yml/enable
```

### 16.6. Bedrock model access revoke (account-level kill, ultimate)

```bash
# Use only if §16.1 does not work and an absolute stop is needed.
# Action at the account level, not at the region level.

# AWS Console → Bedrock → Model access → Manage model access →
# Uncheck Nova Lite / Nova Micro → Save changes.
# Any Bedrock invoke on any model → AccessDeniedException.

# Restore — re-enable in the same place (usually instantaneous for
# already-approved models).
```

This requires an **AWS account owner** (the instructor) — Marat
without console access cannot do it.

---

## 17. Appendix D — Terraform state DR

Terraform state is a **hidden critical dependency** for almost every
recovery scenario (region failover, renaming a restored instance,
IAM-policy rollback). If the state is lost or the lock is stuck —
most runbook procedures are blocked.

**Current configuration (from `terraform/cloud/backend.tf`):**

- Backend: S3 bucket `dmc-1-t2-notebook-terraform-state`;
- Locking: native S3 `use_lockfile = true` (Terraform ≥ 1.10), **no
  DynamoDB**;
- Bucket versioning: enabled (a previous version can be restored).

### 17.1. Scenario: the state object is deleted / corrupted

#### Identify

```bash
cd terraform/cloud
terraform init 2>&1 | head -20
# Signs: "Failed to load state" / "no such file" / unexpected EOF.

# List versions in the bucket
aws s3api list-object-versions \
  --bucket dmc-1-t2-notebook-terraform-state \
  --prefix cloud/terraform.tfstate \
  --query 'Versions[].{VersionId:VersionId,LastModified:LastModified,Size:Size,IsLatest:IsLatest}' \
  --output table
```

#### Recovery

```bash
# Step 1. Find the latest known-good version (not the current one if it is broken)
GOOD_VID="<copy from list-object-versions>"

# Step 2. Restore the object version (copy it into "current")
aws s3api copy-object \
  --bucket dmc-1-t2-notebook-terraform-state \
  --copy-source "dmc-1-t2-notebook-terraform-state/cloud/terraform.tfstate?versionId=${GOOD_VID}" \
  --key cloud/terraform.tfstate

# Step 3. Verify
cd terraform/cloud
terraform init -reconfigure
terraform plan
# The plan should show a no-op or minimal drift.
```

#### RTO

5–15 minutes.

### 17.2. Scenario: the native S3 lock is stuck

#### Identify

```bash
terraform plan 2>&1 | head -10
# "Error: Error acquiring the state lock" / "ConditionalCheckFailedException"
# or "lock file ... exists".
```

#### Recovery

```bash
# Step 1. Check there is no active workflow (infra-cloud.yml)
gh run list --workflow infra-cloud.yml --limit 5 --json status,conclusion,createdAt
# If something is running — wait.

# Step 2. If nothing is active — find the lock file
aws s3 ls "s3://dmc-1-t2-notebook-terraform-state/cloud/" --recursive | grep tflock

# Step 3. Force-unlock via Terraform (preferred)
cd terraform/cloud
terraform force-unlock <LOCK_ID_from_error_message>
# (LOCK_ID — UUID from the error message)

# Step 4. If force-unlock does not work — delete the lock file manually
aws s3 rm "s3://dmc-1-t2-notebook-terraform-state/cloud/terraform.tfstate.tflock"
```

#### RTO

2–5 minutes.

> ⚠ **Never** delete the lock file while a real apply is running from
> another environment. It can leave the state in an inconsistent
> condition. First make sure via `gh run list` that no workflows are
> active.

### 17.3. Scenario: the state bucket is deleted

The worst case.

#### Recovery (if the bucket was versioned — our case)

```bash
# Bucket recovery via AWS Support (if the bucket was deleted less than
# 30 days ago).
# Otherwise — recovery is impossible; need to re-bootstrap the state
# from scratch (`infra-bootstrap.yml` workflow_dispatch) and manually
# `terraform import` every existing resource.
```

RTO without a state backup:

- 4–8 hours (manual import of every resource via `terraform import`);
- Alternative: `terraform destroy` the remaining resources + `apply`
  again → data loss (RDS, secrets — gone).

### 17.4. Follow-ups

- **Cross-region replication of the state bucket** → a copy in
  `eu-west-1` as a safety net against a regional outage / accidental
  delete. Cost ≈ $1/month.
- **State backup in a separate AWS account** of Marat's (if it falls
  in the G.handover scope).
- **Tag the state bucket as critical** + S3 Object Lock (if possible)
  to protect against accidental delete.

---

> End of the runbook. Structure complete: Prerequisites + §1–4 common
> sections + §5–11 scenarios A–G + §12 verification + §13 postmortem
> + §14–17 appendices A/B/C/D.
