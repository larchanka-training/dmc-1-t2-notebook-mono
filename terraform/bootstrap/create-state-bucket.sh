#!/usr/bin/env bash
# Creates the S3 bucket for Terraform state (chicken-and-egg: TF can't create its
# own backend bucket). Idempotent: if the bucket already exists under the current
# account, it just (re)applies versioning/encryption/public-access-block.
#
# Terraform 1.10+ supports native locking in S3 (use_lockfile=true), so DynamoDB
# is no longer needed.
#
# Usage:
#   AWS_REGION=eu-north-1 BUCKET=dmc-1-t2-notebook-terraform-state ./create-state-bucket.sh
#
# Requires: aws-cli v2 and valid AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY
# (or a configured profile).

set -euo pipefail

: "${BUCKET:?BUCKET env required (e.g. dmc-1-t2-notebook-terraform-state)}"
: "${AWS_REGION:?AWS_REGION env required (e.g. eu-north-1)}"

echo "==> Region: ${AWS_REGION}, bucket: ${BUCKET}"

if aws s3api head-bucket --bucket "${BUCKET}" 2>/dev/null; then
  echo "Bucket ${BUCKET} already exists — skipping create."
else
  echo "Creating bucket ${BUCKET} in ${AWS_REGION}..."
  if [ "${AWS_REGION}" = "us-east-1" ]; then
    aws s3api create-bucket --bucket "${BUCKET}" --region "${AWS_REGION}"
  else
    aws s3api create-bucket \
      --bucket "${BUCKET}" \
      --region "${AWS_REGION}" \
      --create-bucket-configuration "LocationConstraint=${AWS_REGION}"
  fi
fi

echo "==> Enabling versioning (needed to roll back tfstate)"
aws s3api put-bucket-versioning \
  --bucket "${BUCKET}" \
  --versioning-configuration Status=Enabled

echo "==> Enabling SSE (AES256, no KMS to avoid needing kms permissions)"
aws s3api put-bucket-encryption \
  --bucket "${BUCKET}" \
  --server-side-encryption-configuration '{
    "Rules": [{
      "ApplyServerSideEncryptionByDefault": {"SSEAlgorithm": "AES256"},
      "BucketKeyEnabled": true
    }]
  }'

echo "==> Blocking public access"
aws s3api put-public-access-block \
  --bucket "${BUCKET}" \
  --public-access-block-configuration \
  'BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true'

echo
echo "Done. Terraform backend:"
echo "  bucket = \"${BUCKET}\""
echo "  region = \"${AWS_REGION}\""
echo "  use_lockfile = true   # native S3 locking, no DynamoDB (TF >= 1.10)"
