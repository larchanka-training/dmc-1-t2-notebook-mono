# Mono-repo DevOps notes

This repository is used for local development and for running all services via Docker Compose.

Per-module CI and its documentation live in the submodule repositories:

- `api/docs/ci-cd.md`
- `ui/docs/ci-cd.md`

`api` and `ui` are **built and published** as separate immutable images
(`api-<tag>` / `ui-<tag>`) to Amazon ECR.

> **Production is deployed cloud-native, not via Docker Compose.** The live prod
> stack is ECS Fargate + RDS + S3/CloudFront (`terraform/cloud`), deployed by
> `deploy-cloud.yml` (auto after `ECR Publish` on `main`, plus manual dispatch for
> rollback). See [`aws-cloud-migration.md`](aws-cloud-migration.md) for the
> authoritative deployment model and [`preview-v2.md`](preview-v2.md) for per-PR
> previews. The `docker-compose.prod.yaml` flow below is a **legacy / manual
> fallback** (e.g. running the prebuilt images on a single host) and is **not**
> how prod is deployed — it is kept for local prod-image smoke tests and as a
> break-glass option.

## Production Docker Compose (legacy / manual fallback)

The production compose runs prebuilt Docker images from Amazon ECR and does not build
`api`/`ui` locally.

Before running the private images, you need to log in to ECR:

```bash
aws ecr get-login-password --region eu-north-1 \
  | docker login --username AWS --password-stdin 867633231218.dkr.ecr.eu-north-1.amazonaws.com
```

Preparing the env file:

```bash
cp .env.prod.example .env.prod
```

Before a production run, replace the `change-me` values in
`.env.prod`. For an actual production run, use an immutable tag:

```bash
IMAGE_TAG=sha-8be47cc
```

Starting:

```bash
docker compose --env-file .env.prod -f docker-compose.prod.yaml pull
docker compose --env-file .env.prod -f docker-compose.prod.yaml up -d
docker compose --env-file .env.prod -f docker-compose.prod.yaml ps
```

Smoke check:

```bash
curl http://localhost/api/v1/health
curl http://localhost/
```

Stopping:

```bash
docker compose --env-file .env.prod -f docker-compose.prod.yaml down
```
