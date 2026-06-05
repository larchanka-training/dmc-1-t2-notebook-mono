# terraform/bootstrap — S3 bucket for Terraform state

This holds the script that **one-time** creates the S3 bucket that stores the
tfstate. It's a chicken-and-egg task: Terraform can't create the very backend it
will use to store its own state.

## What it creates

- S3 bucket `dmc-1-t2-notebook-terraform-state` in `eu-north-1`
- Versioning: ON (needed to roll tfstate back)
- Encryption: AES256 (no KMS — `deploy-user` may lack kms permissions)
- Public access: fully blocked

DynamoDB is **not needed**: with Terraform 1.10+ the S3 backend supports native
locking (`use_lockfile = true`) — the state lock lives in the bucket next to the
state.

## Run (once)

Via CI (preferred):

```text
GitHub Actions → Infra — Bootstrap Terraform state → Run workflow
```

Locally:

```bash
AWS_REGION=eu-north-1 BUCKET=dmc-1-t2-notebook-terraform-state ./create-state-bucket.sh
```

The script is idempotent — re-running breaks nothing (`head-bucket` on an existing
bucket succeeds; versioning/encryption/public-access-block are re-applied).

## What's next

Once the bucket exists, the cloud stacks' root configs (`terraform/cloud/` and
`terraform/preview-cloud/`) are already wired to it via `backend.tf` (each stack
gets its own state key). Run `terraform init` (it picks up the backend) →
`terraform apply`. This is applied through the `infra-cloud.yml` /
`infra-preview-cloud.yml` workflows (`workflow_dispatch`).
