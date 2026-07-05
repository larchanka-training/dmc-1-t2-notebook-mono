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

## TLS / domain

- Public TLS terminates at **Cloudflare** (`jsnb.org`, proxied). Zone SSL mode
  is **Full**, so the origin nginx also listens on **443** with a **Cloudflare
  Origin Certificate** (`jsnb.org`, `*.jsnb.org`, 15 years).
- The certificate pair lives **only on the server** at `proxy/certs/origin.pem`
  / `origin.key` (`chmod 600`); the directory is git-ignored. To reissue:
  Cloudflare → SSL/TLS → Origin Server → Create Certificate.
- nginx also sends the COOP/COEP headers required for `SharedArrayBuffer`
  (notebook cell execution) — see `proxy/nginx.prod.conf`.

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
(`ECR_REGISTRY=ghcr.io/larchanka-training`, generated secrets, Resend and
Bedrock keys). For an actual production run, use an immutable tag:

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
