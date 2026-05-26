#!/usr/bin/env bash
# Создаёт S3-бакет под Terraform state (chicken-and-egg: TF не может сам
# создать свой backend-бакет). Идемпотентно: если бакет уже существует под
# текущим аккаунтом — просто включает на нём versioning/encryption/public-access-block.
#
# Terraform 1.10+ поддерживает native locking в S3 (use_lockfile=true),
# DynamoDB больше не нужен.
#
# Использование:
#   AWS_REGION=eu-north-1 BUCKET=jsnotes-t2-tfstate ./create-state-bucket.sh
#
# Зависимости: aws-cli v2, корректные AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY
# (или конфиг профиля).

set -euo pipefail

: "${BUCKET:?BUCKET env required (e.g. jsnotes-t2-tfstate)}"
: "${AWS_REGION:?AWS_REGION env required (e.g. eu-north-1)}"

echo "==> Регион: ${AWS_REGION}, бакет: ${BUCKET}"

if aws s3api head-bucket --bucket "${BUCKET}" 2>/dev/null; then
  echo "Бакет ${BUCKET} уже существует — пропускаю create."
else
  echo "Создаю бакет ${BUCKET} в ${AWS_REGION}..."
  if [ "${AWS_REGION}" = "us-east-1" ]; then
    aws s3api create-bucket --bucket "${BUCKET}" --region "${AWS_REGION}"
  else
    aws s3api create-bucket \
      --bucket "${BUCKET}" \
      --region "${AWS_REGION}" \
      --create-bucket-configuration "LocationConstraint=${AWS_REGION}"
  fi
fi

echo "==> Включаю versioning (нужно для отката tfstate)"
aws s3api put-bucket-versioning \
  --bucket "${BUCKET}" \
  --versioning-configuration Status=Enabled

echo "==> Включаю SSE (AES256, без KMS, чтобы не упереться в kms-права)"
aws s3api put-bucket-encryption \
  --bucket "${BUCKET}" \
  --server-side-encryption-configuration '{
    "Rules": [{
      "ApplyServerSideEncryptionByDefault": {"SSEAlgorithm": "AES256"},
      "BucketKeyEnabled": true
    }]
  }'

echo "==> Блокирую публичный доступ"
aws s3api put-public-access-block \
  --bucket "${BUCKET}" \
  --public-access-block-configuration \
  'BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true'

echo
echo "Готово. Backend для Terraform:"
echo "  bucket = \"${BUCKET}\""
echo "  region = \"${AWS_REGION}\""
echo "  use_lockfile = true   # native S3 locking, без DynamoDB (TF >= 1.10)"
