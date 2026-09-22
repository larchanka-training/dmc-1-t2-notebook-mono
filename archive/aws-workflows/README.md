# AWS Workflow Archive

**Archived:** 2026-07-05  
**Reason:** Production moved from AWS (ECS Fargate + ECR + S3/CloudFront) to Beget VPS (GHCR + docker compose over SSH).  
**Active tag:** `aws-deploy-archive-2026-07-05` — points to the last commit where these workflows were live.

These files are kept for reference. They are NOT in `.github/workflows/` and therefore do NOT run.

## Files

| File | What it did |
|---|---|
| `ecr-publish.yml` | Triggered build on push to main/tag → called build-images.yml |
| `build-images.yml` | Built api/ui/migrations images → pushed to Amazon ECR |
| `deploy-cloud.yml` | Deployed to ECS Fargate (task-def, migrations, rolling update, S3+CloudFront for UI) |
| `deploy-preview.yml` | Deployed per-PR preview slices to shared ECS + S3/CloudFront |
| `infra-cloud.yml` | Applied Terraform for prod cloud stack (VPC/ECS/ALB/RDS/CloudFront) |
| `infra-preview-cloud.yml` | Applied Terraform for shared preview layer |
| `infra-bootstrap.yml` | One-time S3 state bucket creation for Terraform backend |
| `preview-sweep.yml` | Cleaned up orphaned per-PR preview environments |
| `reset-db.yml` | Reset the preview DB via a one-off ECS task (Secrets Manager + run-task) |

## To restore / study

```bash
git checkout aws-deploy-archive-2026-07-05  # view the state when these were active
git checkout main                            # return to current
```

## Audit and Deprecation Status (larchanka-training/js-notebook#186)

Formally audited under [`larchanka-training/js-notebook#186`](https://github.com/larchanka-training/js-notebook/issues/186) (workflow and secret audit completed; full issue closure pending API default provider migration and host runtime credential revocation):
- **Workflow verification:** All 9 legacy AWS workflows remain safely archived in this directory. No AWS deployment or preview workflows exist in `.github/workflows/`.
- **Secret cleanup:** Confirmed that no `AWS_*` secrets exist in GitHub Actions repository secrets for `dmc-1-t2-notebook-mono`, `dmc-1-t2-notebook-api`, or `dmc-1-t2-notebook-ui`.
- **CI unblocking:** CI pipelines and Dependabot operate entirely independently of AWS credentials.
- **Runtime deprecation:** AWS Bedrock is formally deprecated across project configuration (`.env.prod.example`) and architecture documentation in favor of OpenRouter (`LLM_PROVIDER=openrouter`).
