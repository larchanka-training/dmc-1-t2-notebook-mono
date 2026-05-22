# Manual Deploy Workflow

## Purpose

The deploy workflow prepares the project for a manual deployment from Docker
images published to GHCR.

At the current stage this is a dry-run workflow: it validates the selected
environment, the image tag and the validity of the production Docker Compose
configuration, but does not connect to a server.

Workflow file:

```text
.github/workflows/deploy.yml
```

Related issue:

```text
https://github.com/larchanka-training/dmc-1-t2-notebook-mono/issues/42
```

## How to run

Open GitHub Actions, select `Manual Deploy` and run the workflow manually.

Required inputs:

| Input | Allowed values | Example |
| --- | --- | --- |
| `environment` | `staging`, `production` | `staging` |
| `image_tag` | any valid Docker tag from GHCR | `main`, `sha-8be47cc` |

The workflow uses:

```text
docker-compose.prod.yaml
.env.prod.example
```

The selected `image_tag` is written into a temporary `.env.prod` file during
the workflow run. No secrets are committed to the repository.

## What the workflow checks

The current dry-run job checks that:

- `environment` is either `staging` or `production`;
- `image_tag` is not empty;
- `image_tag` looks like a valid Docker tag;
- the command `docker compose --env-file .env.prod -f docker-compose.prod.yaml config` completes successfully;
- the target environment and the Docker images are printed to the GitHub Actions summary.

Expected image names:

```text
ghcr.io/larchanka-training/js-notebook-api:<image_tag>
ghcr.io/larchanka-training/js-notebook-ui:<image_tag>
```

## GitHub Environments

Two GitHub Environments must be created in the repository settings:

```text
staging
production
```

Recommended settings:

- `staging`: no required reviewers, used to verify the deployment wiring;
- `production`: enable required reviewers before running a production deploy.

The workflow job uses:

```yaml
environment: ${{ inputs.environment }}
```

This makes it possible to add environment-specific secrets for `staging` and
`production` later.

## Future SSH Deploy Secrets

Once a real server exists, these secrets must be added to the appropriate
GitHub Environment rather than stored as plain variables in code:

| Secret | Purpose |
| --- | --- |
| `SSH_HOST` | server hostname or IP address |
| `SSH_USER` | Linux user for the deployment |
| `SSH_PRIVATE_KEY` | private key for SSH authentication |
| `GHCR_USERNAME` | GitHub username or bot account for pulling GHCR images |
| `GHCR_READ_TOKEN` | token with read access to private GHCR packages |

Real secret values must never be committed to git.

## Future SSH Deploy Flow

Once the server is ready, the deploy job can be extended with the following
steps:

1. Connect to the server over SSH.
2. Log in to GHCR:

```bash
echo "${GHCR_READ_TOKEN}" | docker login ghcr.io -u "${GHCR_USERNAME}" --password-stdin
```

3. Pull the selected Docker images:

```bash
docker pull ghcr.io/larchanka-training/js-notebook-api:${IMAGE_TAG}
docker pull ghcr.io/larchanka-training/js-notebook-ui:${IMAGE_TAG}
```

4. Start the production compose:

```bash
IMAGE_TAG=${IMAGE_TAG} docker compose --env-file .env.prod -f docker-compose.prod.yaml up -d
```

5. Run smoke checks:

```bash
curl -fsS https://api.notebook.com/api/v1/health
curl -fsS https://notebook.com/
```

## Rollback

A rollback must use the same manual workflow, but with the previous immutable
image tag, for example:

```text
sha-8be47cc
```

For a production rollback it is better not to use mutable tags such as `main`.

## Current limitation

This workflow does not yet deploy the application to a real server. It only
validates the deploy inputs and the production compose configuration.

SSH deployment must be added as a separate change, once the following are
ready:

- the target server;
- the domain;
- the TLS strategy;
- the production secrets.
