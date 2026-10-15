# Mono-repo DevOps notes

This repository is used for local development and for running all services via Docker Compose.

Per-module CI and its documentation live in the submodule repositories:

- `api/docs/ci-cd.md`
- `ui/docs/ci-cd.md`

`api`, `ui` and `migrations` are **built and published** as separate immutable
images (`api-<tag>` / `ui-<tag>` / `migrations-<tag>`) to **GitHub Container
Registry (GHCR)**: `ghcr.io/larchanka-training/jsnotes-t2`.

> **Production runs on an Aeza VPS via Docker Compose** (cut over from Beget on
> 2026-09-13; the earlier retired AWS stack is documented in
> [`aws-cloud-migration.md`](aws-cloud-migration.md) and snapshotted at git tag
> `aws-deploy-archive-2026-07-05`). `docker-compose.prod.yaml` is the
> **authoritative production deployment**, not a fallback.

## Production pipeline (GHCR + Aeza)

```
push to main (or workflow_dispatch on ghcr-publish.yml)
  → ghcr-publish.yml            (thin trigger, path-filtered to api/**, ui/**, workflows)
    → build-images.yml          (3-phase sequential pipeline in single runner):
        Phase 1: Candidate Build
          - Build candidate-migrations:latest, candidate-api:latest, candidate-ui:latest
          - Load candidates into runner's local Docker daemon (load: true, push: false)
        Phase 2: Validation Health Gate Barrier
          - Boot postgres:16-alpine on ephemeral bridge network
          - Wait for PostgreSQL readiness (pg_isready, 30s timeout)
          - Execute candidate-migrations:latest in production context (contexts=production)
          - Boot candidate-api:latest against gate DB
          - Probe GET /api/v1/health/ready for strict HTTP 200 + database "ok" (validate_gate_readiness.py)
          - Fail fast (exit 1) on HTTP 500, 503, invalid JSON, or degraded component status
          - Trap EXIT to ensure container & network teardown
        Phase 3: Coordinated GHCR Publish
          - Reached ONLY if Phase 2 passes completely
          - Promote exact tested candidate images via docker tag & docker push (zero rebuild)
          - Line-by-line tag processing over env vars (handles multi-tag latest + sha on main)
      → deploy-aeza-production.yml (workflow_run on GHCR Publish success, branches: [main]):
          Environment Gate: Required Reviewers (manual approval pause)
            - Pauses execution before any deployment commands run
            - Operator reviews published tags and explicitly Approves or Rejects release
          Deploy Steps (SSH to Aeza):
            git reset --hard origin/main     # sync compose/nginx config
            docker login ghcr.io             # ephemeral GITHUB_TOKEN
            verify + pull all three images   # immutable tag must exist
            validate rendered config         # prod DB/auth/LLM/image guards
            postgres healthcheck             # wait until the DB accepts connections
            checked pre-deploy pg_dump       # stop if dump/list/checksum fails
            Liquibase migrations             # one-off container, contexts=production,
                                             # deploy FAILS unless it exits 0
            compose up -d                    # rolling restart
            container health gates           # wait for api=healthy and frontend=healthy
            deployed image verification      # api and frontend run requested tag
            origin + public health gates     # api /api/v1/health AND ui root /
                                             # (HTTP 200, <div id="root">, COOP/COEP)
```

- **Registry auth:** the build job pushes with the ephemeral, per-run
  `GITHUB_TOKEN` (`packages: write`); the deploy step passes the same per-run
  token over SSH for `docker pull` — no long-lived registry credentials are
  stored on the server.
- **Rollback:** run `deploy-aeza-production.yml` via `workflow_dispatch` from
  `main` with an explicit
  immutable `image_tag` (`sha-<short>`), never the mutable `latest`.
- **Deploy target:** `/home/deploy/jsnb-production`, Compose project
  `jsnotes-production`, public host `https://jsnb.org`.
- **Required GitHub secrets:** connection material lives only in the
  `aeza-production` Environment; the pre-existing repository `GH_PAT` remains
  limited to private submodule checkout during image builds.
- **Environment Protection (Manual Approval Gate):** the `aeza-production`
  Environment is configured with **Required Reviewers**. Every automated run
  triggered by GHCR Publish pauses in `Waiting for review`, preventing
  accidental or unplanned deployments (e.g. intermediate submodule pointer merges).
  Operators must review and click `Approve and deploy` or `Reject`. Emergency
  rollbacks via `workflow_dispatch` remain available.

Create `aeza-production` under Repository -> Settings -> Environments and add:

| Environment secret | Purpose |
|---|---|
| `AEZA_PRODUCTION_HOST` | Aeza production IPv4/hostname |
| `AEZA_PRODUCTION_USER` | Unprivileged SSH user (`deploy`) |
| `AEZA_PRODUCTION_SSH_KEY` | Dedicated private automation key |
| `AEZA_PRODUCTION_SSH_PASSPHRASE` | Key passphrase, when the key has one |
| `AEZA_PRODUCTION_HOST_FINGERPRINT` | Pinned SSH host-key SHA256 fingerprint |

Restrict the Environment deployment branch policy to `main`. Runtime secrets
remain only in `/home/deploy/jsnb-production/.env.prod` with mode `600`; do not
copy database, auth, email, or OpenRouter credentials into GitHub.

The production workflow is fail closed. It requires `APP_ENV=production`,
`LLM_PROVIDER=openrouter`, `ALLOW_PLACEHOLDER_AUTH=false`,
`ENABLE_EXECUTE=false`, exactly two allowlisted accounts, the real production
Compose database, and the requested immutable API/UI image pair. Expanding the
allowlist remains blocked on application-side usage accounting and quotas.

## Pre-publish validation health gate

The reusable workflow `.github/workflows/build-images.yml` enforces an immutable
artifact promotion pattern across three sequential phases in a single runner job:

1. **Phase 1 (Candidate Build):** Builds `candidate-migrations:latest`,
   `candidate-api:latest`, and `candidate-ui:latest` with `--load` into the
   local Docker daemon. No images are pushed to remote registry in this phase.
2. **Phase 2 (Validation Barrier):** Spins up disposable `postgres:16-alpine`,
   runs candidate Liquibase migrations in `production` context, boots candidate
   API, and probes `GET /api/v1/health/ready`.
   - **Fail-Fast Semantics:** The gate retries only transient connection refusal
     (container boot). If the endpoint returns HTTP 200 with invalid JSON, a
     non-`ok` status, or database connection error,
     `.github/scripts/validate_gate_readiness.py` exits with code 1 immediately.
     HTTP 500/503 responses abort without further retries.
   - **Cleanup:** A shell `trap cleanup EXIT` ensures ephemeral containers and
     networks are destroyed regardless of gate outcome.
3. **Phase 3 (Coordinated Publish):** Only executed if Phase 2 passes. Promotes
   the exact local candidate images to GHCR using `docker tag` and `docker push`.
   Images are never rebuilt from source during publication, guaranteeing
   digest parity between the tested candidate and the deployed artifact.
   Multi-tag outputs from `metadata-action` (e.g. `latest` + `sha-<short>` on `main`)
   are passed via environment variables and iterated line-by-line to prevent
   shell expansion syntax errors.

## Nightly autotests & automated incident lifecycle

The workflow `.github/workflows/autotests.yml` runs the containerized regression
suite nightly at 02:00 UTC on `main` (`autotests/scripts/run-containerized.sh regression`).

To follow the principle of least privilege, permissions are strictly separated:

- **`autotests` job:** Runs the containerized tests with `permissions: contents: read`.
- **`incident-reporter` job:** Runs after `autotests` with
  `permissions: issues: write, actions: read`, restricted to scheduled runs on `main`:
  `if: always() && github.event_name == 'schedule' && github.ref == 'refs/heads/main'`.

### Incident lifecycle (`.github/scripts/incident_reporter.py`)

1. **Failure on main:** If no open incident exists, creates a new issue titled
   `🚨 Nightly Regression Suite Failure on main` labeled `nightly-incident,bug,DevOps`
   with embedded metadata `<!-- incident-metadata: {"run_id": "...", ...} -->`.
2. **Repeated failures:** Appends a comment to the existing open incident issue.
   Deduplicates identical `(run_id, run_attempt)` delivery events to avoid duplicate comments.
3. **Recovery on main:** When a subsequent scheduled run passes, automatically closes
   the open incident with a resolution comment embedding
   `<!-- resolution-metadata: {"resolved_by_run_number": ...} -->`.
4. **Stale rerun protection:**
   - If an older failed rerun arrives for an incident already resolved by a newer run
     (`(run_number, run_attempt) <= (resolved_by_run_number, resolved_attempt)`),
     it is ignored.
   - If no incident was open (all-green history), the reporter queries
     `gh run list --workflow autotests.yml --branch main --event schedule --status success --limit 1`
     to detect whether a subsequent scheduled run has already succeeded. Obsolete
     failed reruns are suppressed, preventing false-alarm incident creation.

The pre-deploy dump is stored under
`/home/deploy/jsnb-deploy-backups/aeza-production`, mode `600`, and copies older
than 14 days are removed. This is a deployment rollback aid only: it does not
replace scheduled encrypted off-host backups and tested restore automation. For
the full backup schedule, off-host replication, and disposable restore verification
runbook, see [`backup-restore.md`](./backup-restore.md).

### Deployment health gates

The workflow enforces multiple independent health checks before marking a deploy successful:

1. **Container health:**
   - `postgres`: waits for PostgreSQL readiness before taking backups or running migrations.
   - `api`: database readiness (`/api/v1/health/ready`) is verified during the dedicated one-off image preflight; the running container's compose healthcheck then verifies service liveness (`/api/v1/health`).
   - `frontend`: validated via explicit Docker Compose healthcheck (`wget -qO- http://127.0.0.1/`) with 5-second polling intervals.
   - `proxy`: depends on both `api` and `frontend` reaching `service_healthy`.
2. **Origin health checks (`127.0.0.1:443` with origin certificate):**
   - API: `/api/v1/health` must return HTTP 200 with `{"status": "ok", "environment": "production"}` via `validate_deploy_health.py`.
   - UI root: `/` must return HTTP 200, contain `<div id="root">`, and include cross-origin isolation headers (`Cross-Origin-Opener-Policy: same-origin`, `Cross-Origin-Embedder-Policy: require-corp`) via `validate_deploy_ui.py`.
3. **Public Cloudflare health checks (`https://jsnb.org`):**
   - API: public `/api/v1/health` verified with retries.
   - UI root: public `/` verified for HTTP 200, root markup, and COOP/COEP isolation headers.

### Rollback and roll-forward operational runbook

The immutable rollback path enables immediate recovery to a previous immutable container image tag:

1. **Triggering rollback or roll-forward:**
   ```bash
   # Roll back to a verified compatible immutable tag (example with sha-7e81b92):
   gh workflow run deploy-aeza-production.yml \
     --repo larchanka-training/dmc-1-t2-notebook-mono \
     --ref main \
     -f image_tag="sha-7e81b92"

   # Roll forward back to target release (example with sha-731ca16):
   gh workflow run deploy-aeza-production.yml \
     --repo larchanka-training/dmc-1-t2-notebook-mono \
     --ref main \
     -f image_tag="sha-731ca16"
   ```
   *Note: Always pass the tag as a quoted string (e.g. `image_tag="sha-7e81b92"`). Do not use unquoted angle brackets `<tag>`, which shell interprets as redirection.*

2. **Execution workflow & operational boundaries:**
   - **Configuration & tooling scope:** The deployment runner synchronizes Compose files and validation scripts from `origin/main` (`git reset --hard origin/main`). The rollback switches the running container image tags (`api`, `frontend`), but does not roll back Compose definitions or deployment scripts.
   - **Pre-deploy backup boundary:** PostgreSQL is started/verified first (`up -d postgres`). The pre-deploy dump is taken *before* Liquibase migrations and *before* promoting or replacing the `api` and `frontend` containers. Dumps are stored under `/home/deploy/jsnb-deploy-backups/aeza-production/`.
   - **In-place container recreation & serving interruption:** The deployment runs `docker compose up -d` against the single-instance production Compose stack. Services are recreated in-place (e.g. `api` and `frontend` recreate, wait for startup, and transition to healthy). There is a brief service interruption window during container recreation; this is **not** a zero-downtime or blue/green deployment.
   - **Post-deployment health gates & failure behavior:** Health checks run sequentially *after* container recreation. If any gate fails (container health, origin health, or public Cloudflare health), the workflow fails closed with exit code 1. On failure, the host remains in its current state (unhealthy containers are not automatically rolled back), and `IMAGE_TAG` in `.env.prod` is **not** updated. The operator must inspect logs (`docker compose logs`) and manually dispatch a rollback to a known-good immutable tag or follow the backup restore procedure.
   - **Tag persistence:** `IMAGE_TAG` is exported in the shell environment during Compose execution and written to `.env.prod` only at the very end after all health gates pass.
   - **Schema boundary:** Liquibase changesets are forward-only. An image rollback succeeds cleanly when the target image code is compatible with the existing database schema. If an incompatible migration was applied, an image rollback alone is insufficient and the backup restore procedure must be followed.

### Verified operational evidence (2026-09-15)

The production deployment, immutable rollback, and roll-forward mechanics were proven on Aeza:

| Operation | Workflow run | Image tag | Result | Health gates verified |
|---|---|---|---|---|
| Automated deploy (`workflow_run`) | [Run 34936010541](https://github.com/larchanka-training/dmc-1-t2-notebook-mono/actions/runs/34936010541) | `sha-731ca16` | Succeeded (42s) | Postgres, API, Frontend container health; Origin + Public API & UI root (COOP/COEP, `<div id="root">`) |
| Immutable rollback (`workflow_dispatch`) | [Run 34936085722](https://github.com/larchanka-training/dmc-1-t2-notebook-mono/actions/runs/34936085722) | `sha-7e81b92` | Succeeded (35s) | Rolled back to `sha-7e81b92`; all container, origin, and public health gates passed |
| Roll-forward (`workflow_dispatch`) | [Run 34936157711](https://github.com/larchanka-training/dmc-1-t2-notebook-mono/actions/runs/34936157711) | `sha-731ca16` | Succeeded (37s) | Rolled forward to `sha-731ca16`; all container, origin, and public health gates passed |

*Operational qualification:* Both tested tags (`sha-7e81b92` and `sha-731ca16`) reference identical submodule gitlinks for `api` (`b3b89c8`) and `ui` (`81a3058`), with zero pending Liquibase changesets. This operational run exercised the workflow dispatch mechanism, container image replacement, configuration guards, backup creation, in-place recreation, and multi-tier health gates. Rollback across backward-incompatible application code versions or schema drift was not exercised and remains governed by the full backup/restore procedure.

## Retired deployment paths

The legacy Beget deployment workflow has been retired and moved to
[`archive/beget-workflows/deploy-beget.yml`](../archive/beget-workflows/deploy-beget.yml) (see also [`archive/beget-workflows/README.md`](../archive/beget-workflows/README.md)).
The historical staging workflow `deploy-aeza-staging.yml` is disabled. Beget no
longer serves the application, and the authoritative `staging.jsnb.org` DNS record
and staging stack were retired during cutover. Do not re-enable either workflow.
Beget secrets (`BEGET_HOST`, `BEGET_USER`, `BEGET_SSH_KEY`) were removed from
GitHub repository secrets on 2026-09-22 following Aeza production qualification
and verification of immutable-tag rollback/roll-forward.

The disabled staging workflow remains in Git only as migration evidence. Its
old `aeza-staging` Environment and secrets are not valid production inputs and
must not be reused by `deploy-aeza-production.yml`.

An immutable image rollback does **not** roll back the PostgreSQL schema:
Liquibase changesets are forward-only in this deployment path. Select only a
previous image that is verified compatible with the current schema. If schema
compatibility is uncertain, stop and use the tested backup/restore procedure
(see [`backup-restore.md`](./backup-restore.md)) instead of dispatching a blind
image rollback.

## TLS / domain

- Public TLS terminates at **Cloudflare** (`jsnb.org`, proxied). Zone SSL mode
  is **Full**, so the origin nginx also listens on **443** with a **Cloudflare
  Origin Certificate** (`jsnb.org`, `*.jsnb.org`, 15 years).
- The certificate pair lives **only on the server** at `proxy/certs/origin.pem`
  / `origin.key` (`chmod 600`); the directory is git-ignored. To reissue:
  Cloudflare → SSL/TLS → Origin Server → Create Certificate.
- nginx also sends the COOP/COEP headers required for `SharedArrayBuffer`
  (notebook cell execution) — see `proxy/nginx.prod.conf`.

## Static asset compression

**Owned by Cloudflare (edge), not the origin.** Cloudflare automatically applies
Brotli/gzip to responses for supporting clients; the origin nginx does **not**
compress. This is a deliberate trade-off: the stock `nginx:alpine` proxy image
ships no Brotli module, and Cloudflare already delivers compressed, cached assets
to end users, so building/maintaining an origin Brotli module buys nothing on the
user-facing path.

Verify (production, end-user path):

```bash
# HTML document
curl -s -I -H 'Accept-Encoding: br, gzip' https://jsnb.org/ | grep -i '^content-encoding\|^server'
# A hashed JS/CSS asset (take a real /assets/*.js from the page source)
curl -s -I -H 'Accept-Encoding: br, gzip' https://jsnb.org/assets/<asset>.js \
  | grep -i '^content-encoding\|^cf-cache-status'
```

Expected: `content-encoding: br` (or `gzip`) and `server: cloudflare`; static
assets also show `cf-cache-status: HIT`. Verified 2026-07-20: both the HTML and
`/assets/*.js` return `content-encoding: br` via Cloudflare.

> If the origin is ever exposed without Cloudflare in front, add `gzip on;` (built
> into stock nginx) to `ui/nginx.conf` as defense-in-depth — Brotli would require
> a custom nginx build and is not currently justified.

## Production Docker Compose (on the VPS)

The production compose runs prebuilt images from GHCR and does not build
`api`/`ui` locally.

Log in to GHCR (only needed for manual pulls; the deploy workflow does this
automatically with an ephemeral token):

```bash
echo "$GHCR_TOKEN" | docker login ghcr.io -u <github-username> --password-stdin
```

Preparing the env file:

```bash
cp .env.prod.example .env.prod
chmod 600 .env.prod
```

Before a production run, replace the `change-me` values in `.env.prod`
(`IMAGE_REGISTRY=ghcr.io/larchanka-training`, generated secrets, Resend, and
the selected LLM provider credentials). For an actual production run, use an
immutable tag:

```bash
IMAGE_TAG=sha-8be47cc
```

Starting (the fixed project name `-p jsnotes-production` keeps the network name
stable for the one-off migration container):

```bash
docker compose -p jsnotes-production --env-file .env.prod -f docker-compose.prod.yaml pull
docker compose -p jsnotes-production --env-file .env.prod -f docker-compose.prod.yaml up -d
docker compose -p jsnotes-production --env-file .env.prod -f docker-compose.prod.yaml ps
```

Smoke check:

```bash
curl http://localhost/api/v1/health
curl -k https://localhost/          # origin TLS (Cloudflare Origin Cert → -k)
```

LLM smoke check:

- For OpenRouter, set `LLM_PROVIDER=openrouter`,
  `LLM_OPENROUTER_API_KEY`, `LLM_OPENROUTER_GENERATOR_MODEL_ID`,
  `LLM_OPENROUTER_GUARD_MODEL_ID`, and a non-empty `LLM_ALLOWED_EMAILS`
  containing only developer accounts.
- The Aeza staging live smoke passed on 2026-08-30. The dynamic
  `openrouter/free` route also produced one transient invalid guard response,
  so a fixed guard model remains a production gate.
- Run the provider smoke procedure in
  [`llm-provider-smoke-test.md`](llm-provider-smoke-test.md) before granting
  access beyond the developer allowlist.

Stopping:

```bash
docker compose -p jsnotes-production --env-file .env.prod -f docker-compose.prod.yaml down
```

## Retired AWS pipeline

The previous ECR + ECS Fargate + S3/CloudFront pipeline (including per-PR
previews) is retired. The workflow files are preserved in
[`archive/aws-workflows/`](../archive/aws-workflows/README.md) and the
Terraform stack in [`terraform/`](../terraform/README-ARCHIVED.md) as
references; the full pre-migration state is at tag
`aws-deploy-archive-2026-07-05`.
