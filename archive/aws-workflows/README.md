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

## To restore / study

```bash
git checkout aws-deploy-archive-2026-07-05  # view the state when these were active
git checkout main                            # return to current
```

See also: `terraform/` directory (infrastructure as code, kept intact for reference).
