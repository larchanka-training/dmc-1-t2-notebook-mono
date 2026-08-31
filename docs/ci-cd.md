# Mono-repo DevOps notes

This repository is used for local development and for running all services via Docker Compose.

Per-module CI and its documentation live in the submodule repositories:

- `api/docs/ci-cd.md`
- `ui/docs/ci-cd.md`

`api`, `ui` and `migrations` are **built and published** as separate immutable
images (`api-<tag>` / `ui-<tag>` / `migrations-<tag>`) to **GitHub Container
Registry (GHCR)**: `ghcr.io/larchanka-training/jsnotes-t2`.

> **Production runs on a Beget VPS via Docker Compose** (migrated off AWS
> 2026-07-05; the retired cloud-native stack is documented in
> [`aws-cloud-migration.md`](aws-cloud-migration.md) and snapshotted at git tag
> `aws-deploy-archive-2026-07-05`). `docker-compose.prod.yaml` is the
> **authoritative production deployment**, not a fallback.

## Production pipeline (GHCR + Beget)

```
push to main
  → ghcr-publish.yml            (thin trigger)
    → build-images.yml          (reusable: api + ui + migrations → GHCR,
                                 tags: <prefix>-latest + <prefix>-sha-<short>)
      → deploy-beget.yml        (workflow_run, SSH to the VPS):
          git reset --hard origin/main     # sync compose/nginx config
          docker login ghcr.io             # ephemeral GITHUB_TOKEN
          compose pull                     # fetch the new images
          postgres healthcheck             # wait until the DB accepts connections
          Liquibase migrations             # one-off container, contexts=production,
                                           # deploy FAILS unless it exits 0
          compose up -d                    # rolling restart
          GET /api/v1/health == 200        # smoke gate
```

- **Registry auth:** the build job pushes with the ephemeral, per-run
  `GITHUB_TOKEN` (`packages: write`); the deploy step passes the same per-run
  token over SSH for `docker pull` — no long-lived registry credentials are
  stored on the server.
- **Rollback:** run `deploy-beget.yml` via `workflow_dispatch` with an explicit
  immutable `image_tag` (`sha-<short>`), never the mutable `latest`.
- **Required GitHub secrets:** `BEGET_SSH_KEY` (dedicated deploy key, not a
  personal one), `BEGET_HOST`, `BEGET_USER`, plus the pre-existing `GH_PAT`
  (submodule checkout during build).

## Aeza staging pipeline

`deploy-aeza-staging.yml` is a separate, manual-only deployment path for
`https://staging.jsnb.org`. It does not replace or trigger
`deploy-beget.yml`. This separation remains in force until the production
migration reaches the cutover gate in
[`aeza-migration-implementation-plan.md`](aeza-migration-implementation-plan.md).

The operator starts the workflow with an explicit immutable tag such as
`sha-9db0e65`. The workflow:

1. rejects mutable or malformed image tags;
2. connects using the `aeza-staging` GitHub Environment;
3. verifies `.env.prod` mode and staging-only runtime guards;
4. synchronizes the server checkout to `origin/main`;
5. verifies all three GHCR images before changing the running stack;
6. pulls API, UI, and migrations images;
7. waits for PostgreSQL health and runs Liquibase migrations;
8. starts the `jsnotes-staging` Compose project;
9. verifies both the local TLS origin and the public Cloudflare endpoint return
   `environment=staging`;
10. logs out of GHCR when the remote script exits.

Create the GitHub Environment at Repository -> Settings -> Environments ->
`aeza-staging`. Add these **environment secrets**:

| Secret | Purpose |
|---|---|
| `AEZA_STAGING_HOST` | Aeza server IPv4/hostname |
| `AEZA_STAGING_USER` | unprivileged SSH deployment user (`deploy`) |
| `AEZA_STAGING_SSH_KEY` | dedicated private deployment key |
| `AEZA_STAGING_SSH_PASSPHRASE` | key passphrase; leave unset only for a deliberately passphrase-free automation key |
| `AEZA_STAGING_HOST_FINGERPRINT` | expected SSH host-key SHA256 fingerprint |

Read the host fingerprint from the already verified server session or the
provider console, not from an unverified first network connection:

```bash
sudo ssh-keygen -lf /etc/ssh/ssh_host_ed25519_key.pub -E sha256
```

Store the `SHA256:...` value as `AEZA_STAGING_HOST_FINGERPRINT`. Use a dedicated
automation key in `AEZA_STAGING_SSH_KEY`; add only its public half to
`/home/deploy/.ssh/authorized_keys` on Aeza.

Runtime application secrets remain only in the server-side `.env.prod`
(`chmod 600`). They are not copied into GitHub Actions. The workflow requires
`APP_ENV=staging`, `LLM_PROVIDER=openrouter`, `ENABLE_EXECUTE=false`, a non-empty
OpenRouter key, and a non-empty developer allowlist before deployment proceeds.

Initial use is manual by design. Do not add `workflow_run` or a `push` trigger
until the staging deployment and rollback have both been exercised and the
production migration plan explicitly approves automation.

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

Starting (the fixed project name `-p jsnotes` keeps the network name stable for
the one-off migration container):

```bash
docker compose -p jsnotes --env-file .env.prod -f docker-compose.prod.yaml pull
docker compose -p jsnotes --env-file .env.prod -f docker-compose.prod.yaml up -d
docker compose -p jsnotes --env-file .env.prod -f docker-compose.prod.yaml ps
```

Smoke check:

```bash
curl http://localhost/api/v1/health
curl -k https://localhost/          # origin TLS (Cloudflare Origin Cert → -k)
```

LLM smoke check:

- Beget production keeps its reviewed provider configuration until the planned
  production cutover; do not switch it as part of staging work.
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
docker compose -p jsnotes --env-file .env.prod -f docker-compose.prod.yaml down
```

## Retired AWS pipeline

The previous ECR + ECS Fargate + S3/CloudFront pipeline (including per-PR
previews) is retired. The workflow files are preserved in
[`archive/aws-workflows/`](../archive/aws-workflows/README.md) and the
Terraform stack in [`terraform/`](../terraform/README-ARCHIVED.md) as
references; the full pre-migration state is at tag
`aws-deploy-archive-2026-07-05`.
