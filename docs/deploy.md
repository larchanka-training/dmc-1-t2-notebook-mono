# Deploy Workflow

## Назначение

Деплой прод-окружения из Docker-образов, опубликованных в Amazon ECR, на
постоянный EC2-хост по SSH. Состоит из двух частей:

1. **Bootstrap хоста** — `infra-prod.yml` создаёт прод-сервер один раз.
2. **Выкат** — `deploy.yml` при каждом обновлении заходит на хост по SSH и
   обновляет контейнеры (`docker compose pull && up -d`).

> **Почему без Terraform.** Terraform требует remote state (S3 + DynamoDB), а у
> `deploy-user` нет прав `s3:CreateBucket` / `dynamodb:CreateTable` (проверено).
> Поэтому прод поднимается императивно (AWS CLI в CI) — это рабочий план Б при
> текущих правах. Подробнее о правах — раздел «Права deploy-user» ниже и
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
.github/workflows/infra-prod.yml   # разовый bootstrap хоста
.github/workflows/deploy.yml       # выкат по SSH (+ dry-run fallback)
```

## Bootstrap прод-хоста (разово)

`infra-prod.yml` (`workflow_dispatch`) под `deploy-user`:

1. Находит default VPC/subnet и свежий Ubuntu 22.04 AMI.
2. Создаёт security group `jsnotes-t2-prod-sg`, открывает порты **22** и **80**.
3. Запускает `t3.micro` с user-data (ставит Docker + docker-compose-plugin,
   кладёт публичный SSH-ключ в `authorized_keys`, создаёт `~/app`).
4. Выводит **Public IP** в Summary.

Идемпотентность — **по членству в SG** (`jsnotes-t2-prod-sg`), а не по тегам:
`ec2:CreateTags` у `deploy-user` запрещён, поэтому инстанс не тегируется. Если в
этой SG уже есть running-инстанс — повторный запуск ничего не создаёт.

Ключ создаётся локально (`ssh-keygen`): публичная половина **зашита в user-data**
`infra-prod.yml` (публичный ключ не секрет), приватная — в secret
`SSH_PRIVATE_KEY` (её использует `deploy.yml`).

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

## Права deploy-user (проверено)

| Действие | Право | Статус |
| --- | --- | --- |
| Создать инстанс | `ec2:RunInstances` | ✅ |
| Создать SG | `ec2:CreateSecurityGroup` | ✅ |
| Открыть порты | `ec2:AuthorizeSecurityGroupIngress` | ✅ |
| Pull/push ECR | `ecr:*` | ✅ |
| Тегировать | `ec2:CreateTags` | ❌ |
| Удалять/гасить | `ec2:TerminateInstances` / `StopInstances` / `DeleteSecurityGroup` | ❌ |
| Terraform state | `s3:CreateBucket` / `dynamodb:CreateTable` | ❌ |
| Instance role | `iam:CreateRole` | ❌ |

Следствия для прода: без тегов (idempotency по SG), без авто-удаления (прод
постоянный; снести при необходимости — из консоли), ECR-логин ключами через SSH.
Запрет `Terminate`/`DeleteSecurityGroup` блокирует **preview** (нужен снос
окружения на закрытии PR) — запрошено у админа, см.
[`preview.md`](preview.md).
