# Mono-repo DevOps notes

This repository is used for local development and for running all services via Docker Compose.

The CI/CD and deployment documentation is located inside separate submodules:

- `api/docs/ci-cd.md`
- `ui/docs/ci-cd.md`

The frontend and backend are deployed separately.

## Production Docker Compose

The production compose runs prebuilt Docker images from GHCR and does not build
`api`/`ui` locally.

Before running the private images, you need to log in to GHCR:

```bash
gh auth token | docker login ghcr.io -u <github-username> --password-stdin
```

Preparing the env file:

```bash
cp .env.prod.example .env.prod
```

Before a shared/staging/production run, replace the `change-me` values in
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
