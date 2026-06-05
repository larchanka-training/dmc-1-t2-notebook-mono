# terraform/bootstrap — S3-бакет под Terraform state

Здесь живёт скрипт, который **разово** создаёт S3-бакет для хранения tfstate.
Это chicken-and-egg-задача: Terraform не может сам создать backend, в котором
он же будет хранить свой state.

## Что создаётся

- S3-бакет `dmc-1-t2-notebook-terraform-state` в `eu-north-1`
- Versioning: ON (нужно для отката tfstate)
- Encryption: AES256 (без KMS — у `deploy-user` могут отсутствовать kms-права)
- Public access: полностью заблокирован

DynamoDB **не нужен**: с Terraform 1.10+ S3-бэкенд поддерживает native locking
(`use_lockfile = true`), state-лок хранится в самом бакете рядом со state'ом.

## Запуск (один раз)

Через CI (предпочтительно):

```text
GitHub Actions → Infra — Bootstrap Terraform state → Run workflow
```

Локально:

```bash
AWS_REGION=eu-north-1 BUCKET=dmc-1-t2-notebook-terraform-state ./create-state-bucket.sh
```

Скрипт идемпотентен — повторный запуск ничего не ломает (`head-bucket` на
существующий бакет проходит, versioning/encryption/PAB переустанавливаются).

## Что дальше

После того как бакет создан, корневые конфиги облачных стеков (`terraform/cloud/`
и `terraform/preview-cloud/`) уже настроены на этот бакет через `backend.tf`
(каждый стек — свой ключ state). Можно запускать `terraform init` (он подхватит
backend) → `terraform apply`. Применяется это через воркфлоу `infra-cloud.yml` /
`infra-preview-cloud.yml` (`workflow_dispatch`).
