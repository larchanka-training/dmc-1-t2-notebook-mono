# Terraform — AWS Infrastructure (Archived Reference)

**Status:** Legacy / archived as of 2026-07-05.  
**Production** has moved to Beget VPS. This Terraform code is kept as a reference and learning resource — it is **not applied** and **not maintained**.

**Archive tag:** `aws-deploy-archive-2026-07-05`

## What this managed

- `terraform/cloud/` — prod stack: VPC, ECS Fargate, ALB, RDS PostgreSQL, S3, CloudFront
- `terraform/preview-cloud/` — shared preview layer (per-PR environments)
- `terraform/modules/` — reusable modules (network, backend, frontend, bastion, data)

## Why kept

- Reference for understanding the original cloud architecture
- Useful if a new AWS account is set up later
- Documents infrastructure decisions (NAT, ECS task definitions, Bedrock VPC endpoints, etc.)

## To study

```bash
git checkout aws-deploy-archive-2026-07-05  # see the state when this was live
# then browse terraform/ freely
git checkout main  # return
```

See `docs/aws-cloud-migration.md` for the full architecture description.
