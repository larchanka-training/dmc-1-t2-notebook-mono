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
push to main
  → ghcr-publish.yml            (thin trigger)
    → build-images.yml          (reusable: api + ui + migrations → GHCR,
                                 tags: <prefix>-latest + <prefix>-sha-<short>)
      → deploy-aeza-production.yml (workflow_run, SSH to Aeza):
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
Beget secrets (`BEGET_HOST`, `BEGET_USER`, `BEGET_SSH_KEY`) are safe to remove from
GitHub repository secrets now that the Aeza production workflow has completed
successful deploy, health verification, and immutable-tag rollback/roll-forward
(verified on 2026-09-15 in runs 34936085722 and 34936157711).

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
