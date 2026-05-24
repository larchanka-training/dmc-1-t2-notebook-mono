# AWS Infrastructure

## Current Status

**AWS is not deployed.** As of May 2026, the project runs entirely on GitHub-hosted infrastructure
(GitHub Actions, GitHub Container Registry). The existing `deploy.yml` workflow is a **dry-run**
only: it validates inputs and the production Compose configuration but does not connect to any
server.

The placeholder for AWS is documented in `docs/github-repository-settings.md` (Handoff section):

> What is not part of the current scope: AWS deploy, AWS IAM/OIDC roles, ECR vs GHCR registry
> decision, domain/TLS, monitoring/logging.

---

## What Is Currently Deployed

| Layer | Technology | Where |
| --- | --- | --- |
| CI (lint, test, build) | GitHub Actions | github.com/larchanka-training/dmc-1-t2-notebook-mono |
| Docker image registry | GitHub Container Registry (GHCR) | ghcr.io/larchanka-training/ |
| Production runtime | Docker Compose | **no server yet** |
| Database | PostgreSQL 16 (Docker container) | **no server yet** |
| Reverse proxy | Nginx 1.27 (Docker container) | **no server yet** |

Docker images published to GHCR:

```
ghcr.io/larchanka-training/js-notebook-api:<tag>
ghcr.io/larchanka-training/js-notebook-ui:<tag>
```

Tags: `main` (mutable, latest main branch), `sha-<short>` (immutable, per-commit),
`v*.*.*` (semver releases), `latest` (default branch alias).

---

## Planned AWS Scope (Next Sprint)

The following items are the expected AWS deliverables based on existing project documentation:

### Compute

| Option | Notes |
| --- | --- |
| EC2 instance (single) | Simplest path; run `docker-compose.prod.yaml` via SSH |
| ECS Fargate | Managed containers; no SSH needed; higher cost at small scale |

The existing production Compose file (`docker-compose.prod.yaml`) is the deploy unit.
It starts four containers: `frontend`, `api`, `postgres`, `proxy` (Nginx on port 80).

### Container Registry

Currently GHCR. The decision between GHCR and AWS ECR is open:

| Option | Pro | Con |
| --- | --- | --- |
| GHCR (current) | No migration needed, already working | Pulling from EC2 requires a GitHub token |
| AWS ECR | Native AWS auth (IAM), no extra tokens | Requires ECR push in CI, migration effort |

If ECR is chosen, the `docker-publish.yml` workflow must be updated to push to ECR in addition
to or instead of GHCR, and the deploy workflow must pull from ECR.

### Database

PostgreSQL currently runs as a Docker container on the same host. For production:

| Option | Notes |
| --- | --- |
| Docker container (current model) | Simple; no extra cost; data loss risk if container removed |
| Amazon RDS for PostgreSQL | Managed backups, snapshots, Multi-AZ; separate cost |

If RDS is used, the `DATABASE_URL` environment variable is the only change needed in
`.env.prod` — the application code is database-URL-agnostic.

### Networking / TLS

No domain or TLS is configured yet. Required additions:

- Route 53 or external DNS pointing to the EC2 Elastic IP
- ACM certificate (if using ALB or CloudFront) or Let's Encrypt / Certbot (on the instance)
- Nginx `nginx.prod.conf` update to terminate HTTPS

### IAM / Access for GitHub Actions

To avoid long-lived AWS credentials in GitHub Secrets, use OIDC:

```yaml
permissions:
  id-token: write
  contents: read

- uses: aws-actions/configure-aws-credentials@v4
  with:
    role-to-assume: arn:aws:iam::<account-id>:role/github-actions-deploy
    aws-region: eu-central-1
```

Required IAM role trust policy:

```json
{
  "Effect": "Allow",
  "Principal": { "Federated": "arn:aws:iam::<account-id>:oidc-provider/token.actions.githubusercontent.com" },
  "Action": "sts:AssumeRoleWithWebIdentity",
  "Condition": {
    "StringEquals": {
      "token.actions.githubusercontent.com:aud": "sts.amazonaws.com"
    },
    "StringLike": {
      "token.actions.githubusercontent.com:sub": "repo:larchanka-training/dmc-1-t2-notebook-mono:*"
    }
  }
}
```

---

## Secrets Required Before a Real Deploy

These must be added to the GitHub Environment (`staging` or `production`) before the
`deploy.yml` workflow can perform real SSH deployment:

| Secret | Purpose | Where to store |
| --- | --- | --- |
| `SSH_HOST` | EC2 public IP or hostname | GitHub Environment secret |
| `SSH_USER` | Linux user on the instance (e.g. `ubuntu`) | GitHub Environment secret |
| `SSH_PRIVATE_KEY` | Private key for SSH auth | GitHub Environment secret |
| `GHCR_USERNAME` | GitHub username for pulling GHCR images | GitHub Environment secret |
| `GHCR_READ_TOKEN` | PAT with `read:packages` scope | GitHub Environment secret |
| `POSTGRES_PASSWORD` | Production DB password | GitHub Environment secret / `.env.prod` |
| `OAUTH_NAME_APPLICATION_ID` | OAuth app ID | GitHub Environment secret / `.env.prod` |
| `OAUTH_NAME_SECRET_KEY` | OAuth secret | GitHub Environment secret / `.env.prod` |

Do **not** commit real secret values to git. The `.env.prod.example` file contains only
placeholder `change-me` values and is safe to commit.

---

## Accounts and Access

| Resource | Account / Owner | Notes |
| --- | --- | --- |
| GitHub organization | larchanka-training | Hosts all three repos and GitHub Actions runners |
| GHCR images | larchanka-training | Published automatically by `docker-publish.yml` on push to `main` |
| AWS account | **not created yet** | Will be needed for EC2 / RDS / Route 53 |
| Domain | **not registered yet** | Required for TLS and public access |
| GH_PAT | repository secret | Used by CI to check out private submodules; min scopes: `repo` read |

---

## Rollback Strategy

The existing documentation (`docs/deploy.md`) defines rollback:

1. Trigger `Manual Deploy` workflow with the previous immutable tag (e.g. `sha-8be47cc`).
2. Do **not** use the `main` mutable tag for production rollbacks.
3. For a real SSH deploy, the rollback runs the same `docker compose up -d` with the old tag.

---

## Step-by-Step: First Real AWS Deploy

When a server is ready, these are the minimum steps to go live:

1. **Provision EC2** — Amazon Linux 2023 or Ubuntu 24.04; install Docker and Docker Compose plugin.
2. **Allocate Elastic IP** — associate with the instance so the IP does not change on restart.
3. **Security group** — open port 80 (HTTP) and 443 (HTTPS) inbound; restrict port 22 (SSH) to known IPs.
4. **Add GitHub Environment secrets** — `SSH_HOST`, `SSH_USER`, `SSH_PRIVATE_KEY`, `GHCR_USERNAME`, `GHCR_READ_TOKEN`.
5. **Add application secrets** — `POSTGRES_PASSWORD`, `OAUTH_NAME_APPLICATION_ID`, `OAUTH_NAME_SECRET_KEY` to the `.env.prod` on the server (or via GitHub Secrets + CI templating).
6. **Update `deploy.yml`** — replace the dry-run `validate` job with real SSH steps (template is in `docs/deploy.md`).
7. **Configure DNS** — point your domain to the Elastic IP.
8. **Configure TLS** — add Certbot to the instance or use ACM + ALB.
9. **Update `nginx.prod.conf`** — add HTTPS server block.
10. **Run `Manual Deploy`** — select `staging`, verify smoke checks pass.
11. **Run `Manual Deploy`** — select `production` after reviewer approval.

---

## Related Files

| File | Purpose |
| --- | --- |
| `docker-compose.prod.yaml` | Production service definitions (images from GHCR) |
| `.env.prod.example` | Template for production env variables |
| `.github/workflows/deploy.yml` | Manual deploy workflow (currently dry-run) |
| `.github/workflows/docker-publish.yml` | Publishes Docker images to GHCR |
| `proxy/nginx.prod.conf` | Nginx config for production Compose |
| `docs/deploy.md` | Deploy runbook and SSH deploy template |
| `docs/github-repository-settings.md` | GitHub Environments, secrets, and CI/CD settings |
