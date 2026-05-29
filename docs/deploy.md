# Deploy Workflow

## Назначение

Деплой прод-окружения из Docker-образов, опубликованных в Amazon ECR, на
постоянный EC2-хост по SSH. Состоит из трёх частей:

1. **Bootstrap state** — `infra-bootstrap.yml` создаёт S3-бакет
   `dmc-1-t2-notebook-terraform-state` под Terraform state (разово).
2. **Bootstrap хоста** — `infra-prod.yml` через Terraform поднимает прод-сервер
   (или импортирует уже существующий, если был создан старой императивной
   версией). Использует модуль `terraform/modules/docker_host`.
3. **Выкат** — `deploy.yml` при каждом обновлении заходит на хост по SSH и
   обновляет контейнеры (`docker compose pull && up -d`).

> **Terraform.** Backend — S3 (`dmc-1-t2-notebook-terraform-state`) с native locking
> (`use_lockfile = true`, Terraform ≥ 1.10). DynamoDB-таблицы для locking
> **не используем** (фича Terraform 1.10+). Конфиги — в `terraform/prod/`.
> Подробнее — [`preview.md`](preview.md) и
> [`preview-dev-environments-v2.md`](preview-dev-environments-v2.md).

## Поток деплоя (на `main`)

```
push в main
   └─► ECR Publish (ecr-publish.yml) — собирает api-/ui-latest в ECR
          └─► Deploy (deploy.yml, workflow_run после ECR Publish)
                 ├─ runner: aws ecr get-login-password  (токен ECR)
                 ├─ ssh на хост → docker login (токен через stdin)
                 ├─ scp docker-compose.prod.yaml + proxy/ + .env.prod → ~/app
                 ├─ docker compose pull && up -d --remove-orphans
                 └─ smoke: curl http://<host>/api/v1/health
```

Если SSH-секреты не заданы — `deploy.yml` остаётся в **dry-run** (только
валидация тега и compose, на сервер не ходит). Это безопасный дефолт.

Файлы workflow:

```text
.github/workflows/infra-bootstrap.yml  # разово: S3-бакет под Terraform state
.github/workflows/infra-prod.yml       # terraform apply прод-хоста (+ import существующего)
.github/workflows/deploy.yml           # выкат по SSH (+ dry-run fallback)
```

## Bootstrap state (разово)

`infra-bootstrap.yml` (`workflow_dispatch`) создаёт S3-бакет
`dmc-1-t2-notebook-terraform-state` с versioning, SSE-AES256 и block-public-access. Скрипт —
`terraform/bootstrap/create-state-bucket.sh`, идемпотентен.

Locking — **в самом S3** (`use_lockfile = true`). DynamoDB не нужен.

## Bootstrap прод-хоста (Terraform)

`infra-prod.yml` (`workflow_dispatch` или push в `ci/aws-deploy` для теста)
выполняет:

1. `terraform init` — backend S3 (state-бакет должен быть создан заранее).
2. **Если в state ещё нет ресурсов**, ищет существующий SG
   `jsnotes-t2-prod-sg` и running-EC2 в нём → делает `terraform import`. Это
   единственный способ принять управление над хостом, который ранее создавал
   старый императивный workflow, не пересоздавая его.
3. `terraform plan -detailed-exitcode` — экзит-код 1 валит workflow (страховка
   от непреднамеренных destructive-изменений).
4. `terraform apply` — создаёт хост, если его не было; иначе no-op.
5. Печатает `public_ip` / `instance_id` в Summary — это значения для секрета
   `SSH_HOST` в `deploy.yml`.

Хост поднимается через модуль `terraform/modules/docker_host`:
default VPC/subnet, свежий Ubuntu 22.04 AMI (Canonical), SG с портами **22+80**,
user-data ставит Docker + docker-compose-plugin и кладёт SSH-ключ ubuntu.
`lifecycle.ignore_changes = [ami, user_data]` — обновление базового AMI или
рефакторинг скрипта **не** триггерит пересоздание прода.

Ключ создаётся локально (`ssh-keygen`): публичная половина зашита в env
`PROD_SSH_PUBLIC_KEY` внутри `infra-prod.yml` (публичный ключ не секрет),
приватная — в secret `SSH_PRIVATE_KEY` (её использует `deploy.yml`).

## Как запускать выкат

**Авто:** после merge в `main` и успешного `ECR Publish` деплой запускается сам
(`workflow_run`, тег `latest`, окружение `production`). Если у окружения
`production` включены required reviewers — ждёт ручного approval.

**Вручную** (откат или конкретный тег): GitHub Actions → `Deploy` → Run workflow.

| Input | Допустимые значения | Пример |
| --- | --- | --- |
| `image_tag` | tag из ECR без префикса `api-`/`ui-` | `latest`, `sha-8be47cc` |

## Secrets (repository)

Реальный выкат включается, только когда заданы все четыре:

| Secret | Назначение |
| --- | --- |
| `SSH_HOST` | публичный IP прод-хоста (из Summary `infra-prod`) |
| `SSH_USER` | linux-пользователь (`ubuntu`) |
| `SSH_PRIVATE_KEY` | приватная половина ключа `jsnotes_prod` |
| `PROD_ENV_FILE` | полное содержимое `.env.prod` (реальные пароли БД/OAuth/TTL) |

Плюс используются (на уровне репозитория/организации): `AWS_ACCESS_KEY_ID`,
`AWS_SECRET_ACCESS_KEY` (для `aws ecr get-login-password`), vars `AWS_REGION`.

ECR-токен берётся **на раннере** и передаётся в `docker login` на хосте через
stdin — на диск хоста токен не пишется. Instance IAM role не используется
(`iam:CreateRole` у `deploy-user` запрещён).

## Что делает деплой (реальный режим)

1. `Decide deploy mode` → `real`, если есть все SSH-секреты + `PROD_ENV_FILE`.
2. Валидирует `image_tag` и `docker compose ... config`.
3. Собирает `.env.prod` из `PROD_ENV_FILE` (переопределяет `IMAGE_TAG`/`ECR_REGISTRY`).
4. Готовит SSH (ключ + `ssh-keyscan`).
5. `scp` `docker-compose.prod.yaml`, `proxy/nginx.prod.conf`, `.env.prod` → `~/app`.
6. На хосте: `docker login` ECR → `docker compose pull` → `up -d --remove-orphans` → `image prune -f`.
7. Smoke: `curl http://<host>/api/v1/health` (с ретраями).

Ожидаемые имена образов:

```text
867633231218.dkr.ecr.eu-north-1.amazonaws.com/jsnotes-t2:api-<image_tag>
867633231218.dkr.ecr.eu-north-1.amazonaws.com/jsnotes-t2:ui-<image_tag>
```

## Адрес

Без домена/TLS — голый HTTP по публичному IP:

```text
http://<SSH_HOST>/            # UI
http://<SSH_HOST>/api/v1/...  # API (через тот же nginx)
```

IP стабилен, пока инстанс не stop/start. Elastic IP / домен / TLS — отдельная
задача.

## Rollback

Тот же `Deploy` (manual `workflow_dispatch`) с предыдущим **immutable** тегом,
например `sha-8be47cc` (не mutable `latest`/`main`).

## GitHub Environments

В проекте одно окружение — `production` (staging нет). На него можно повесить
required reviewers, чтобы авто-деплой после merge ждал ручного approval.

## Права deploy-user (проверено 2026-05-26)

| Действие | Право | Статус |
| --- | --- | --- |
| Создать инстанс | `ec2:RunInstances` | ✅ |
| Создать SG | `ec2:CreateSecurityGroup` | ✅ |
| Открыть порты | `ec2:AuthorizeSecurityGroupIngress` | ✅ |
| Pull/push ECR | `ecr:*` | ✅ |
| Тегировать | `ec2:CreateTags` | ✅ |
| Удалять/гасить | `ec2:TerminateInstances` / `DeleteSecurityGroup` | ✅ (нужно для preview teardown) |
| Terraform state (S3) | `s3:CreateBucket` / `s3:PutObject` | ✅ |
| Instance role | `iam:CreateRole` | ❌ (не используем — ECR-логин через SSH) |
| DynamoDB lock | `dynamodb:CreateTable` | ❌ (не нужен — `use_lockfile=true`) |

Прод выкатывается на постоянный хост (`Terminate` для прода в CI не запускаем —
это ручная операция через консоль или явный TF-destroy). ECR-логин делает
CI-раннер и пробрасывает токен через SSH — instance IAM role не требуется
(`iam:CreateRole` запрещён).
