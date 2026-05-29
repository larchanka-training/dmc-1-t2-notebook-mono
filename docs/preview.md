# Preview-окружения (per-PR) — CI/CD слой

> **Статус:** реализовано на Terraform. Каждый PR получает свой EC2 + SG,
> поднимаемый через `terraform apply` (workspace `pr-<N>`), и удаляется через
> `terraform destroy` при закрытии PR. Preview-URL — `http://<ip>/`,
> без домена и TLS (по решению из decision-дока).

## Идея

Каждый pull request получает свои Docker-образы (`api-pr-<N>` / `ui-pr-<N>` в
ECR) и свой эфемерный EC2-хост. Окружение живёт, пока открыт PR. URL
публикуется sticky-комментарием в самом PR.

## Workflow-файлы

| Файл | Роль |
| --- | --- |
| `.github/workflows/infra-bootstrap.yml` | **Разово** (`workflow_dispatch`): создаёт S3-бакет `dmc-1-t2-notebook-terraform-state` под Terraform state (versioning + SSE-AES256 + public-access-block) |
| `.github/workflows/build-images.yml` | **Reusable** (`workflow_call`): собирает api+ui → ECR. Единственный источник логики сборки |
| `.github/workflows/ecr-publish.yml` | Тонкий триггер на push `main` / тег → вызывает `build-images.yml` (prod-образы) |
| `.github/workflows/preview.yml` | На `pull_request` → вызывает `build-images.yml` (`pr-<N>`), затем `terraform apply` workspace `pr-<N>` + SSH-выкат + sticky-комментарий с URL; на `closed` → `terraform destroy` + удаление workspace |
| `.github/workflows/docker-compose-ci.yml` | Интеграционный smoke-тест стека на PR (без изменений) |

Сборка вынесена в reusable, чтобы prod и preview **не дублировали** шаги.

## Terraform-инфраструктура

Структура `terraform/`:

```
terraform/
├── bootstrap/        # bash-скрипт, создающий S3-бакет под tfstate
├── modules/
│   └── docker_host/  # reusable: EC2 + SG + user-data (Docker + SSH-ключ)
├── prod/             # один state, импортирует существующий прод-хост
└── preview/          # workspace per PR (pr-<N>), свой EC2 + SG на каждый PR
```

Backend — **S3 с native locking** (Terraform ≥ 1.10):

```hcl
backend "s3" {
  bucket       = "dmc-1-t2-notebook-terraform-state"
  key          = "preview/terraform.tfstate"
  region       = "eu-north-1"
  use_lockfile = true   # native S3 lock — DynamoDB не нужен
  encrypt      = true
}
```

DynamoDB-таблица для locking больше не используется. Lock-файл хранится в
самом бакете рядом со state (фича Terraform 1.10).

> **Имя бакета — по конвенции курса:** `dmc-1-t<команда>-notebook-terraform-state`
> (у нас `dmc-1-t2-notebook-terraform-state`). IAM-политика `deploy-user`
> выдаёт S3-доступ именно на это имя — произвольное имя даст `403`.

## Имена ресурсов

Два независимых «имени» у каждого окружения:

| Что | Откуда | Можно ли менять |
| --- | --- | --- |
| **group-name SG** | `var.name` (+ суффикс `-sg`) | ❌ immutable (ForceNew) — смена пересоздаёт SG |
| **Name-тег EC2** | `var.name_tag` (в консоли AWS) | ✅ меняется in-place |

Они **развязаны** намеренно: имя SG нельзя сменить, не пересоздав SG (а его
нельзя удалить, пока он привязан к живому EC2). Поэтому осмысленное имя в консоли
несёт **Name-тег**, а не group-name.

Конвенция Name-тегов команды:

| Окружение | `var.name` (→ group-name SG) | `var.name_tag` (→ Name EC2) |
| --- | --- | --- |
| prod | `jsnotes-t2-prod` → `jsnotes-t2-prod-sg` | `TARDIS-T2-prod` |
| preview | `jsnotes-preview-pr-<N>` → `…-sg` | `TARDIS-T2-preview-pr-<N>` |

`name_tag` для preview берётся из `terraform.workspace` (= `pr-<N>`), поэтому
подставляется автоматически. На проде `name_tag` совпадает с уже существующим
тегом → `apply` не вызывает churn.

## Теги (выбираются `metadata-action` по событию)

| Событие | Теги в ECR `jsnotes-t2` |
| --- | --- |
| push `main` | `api-/ui-latest` + `api-/ui-sha-<short>` |
| тег `v*.*.*` | `api-/ui-<semver>` |
| `pull_request` | `api-/ui-pr-<N>` (репо MUTABLE → перезаписывается на каждый push в PR) |

Preview собирается из тех же Docker-таргетов, что и prod (`api → runtime`,
`ui → production`), — чтобы preview зеркалил прод, а не dev-сборку.

## Жизненный цикл preview

На каждый PR (`opened`/`synchronize`/`reopened`):

1. `build` — собираются и пушатся `api-pr-<N>` / `ui-pr-<N>` в ECR.
2. `deploy` — последовательно:
   - `terraform init` → `workspace select/new pr-<N>` → `apply`;
   - ждём cloud-init (Docker готов через SSH, до 5 минут);
   - `scp` `docker-compose.prod.yaml` + `proxy/nginx.prod.conf` + `.env.prod` → `~/app`;
   - на хосте: `docker login` ECR (токен с раннера через stdin) → `compose pull` → `up -d`;
   - smoke: `curl http://<ip>/api/v1/health`;
   - sticky-комментарий с **рабочим Preview URL** в PR.

На закрытии PR (`closed`):

3. `teardown` — `terraform destroy` + `workspace delete pr-<N>` + обновление комментария.

Concurrency:
- `preview-<N>-deploy`, `cancel-in-progress: true` — новый push в PR
  отменяет прошлую сборку preview.
- `preview-<N>-teardown` — **не** отменяется build/deploy (важно: иначе
  можно оставить инстанс без destroy).

## .env для preview

Берётся из секрета `PROD_ENV_FILE` (тот же, что и для прода). Workflow на
лету переопределяет `IMAGE_TAG=pr-<N>` и `ECR_REGISTRY=...`. Это даёт
preview-окружениям такие же значения OAUTH/POSTGRES/TTL, как у прода —
осознанный компромисс на время курса (стейджа нет). Если позже понадобится
изолированный набор `.env` под preview — заводим отдельный secret.

Файл кладётся в **корень репо** как `.env.prod` (а не в `terraform/preview/`):
`docker-compose.prod.yaml` ссылается на `./.env.prod` через `env_file:` у сервиса
`api`, поэтому файл должен лежать рядом с compose-файлом — иначе
`docker compose config` падает с `env file ./.env.prod not found`.

## Что нужно один раз перед первым PR

1. Запустить `Infra — Bootstrap Terraform state` (`workflow_dispatch`),
   чтобы создать S3-бакет.
2. Запустить `Infra — Provision prod host (Terraform)` — он импортирует
   уже существующий прод-EC2/SG в state (либо создаст, если их нет).

После этого открытие PR автоматически поднимает preview, закрытие — сносит.

## Секреты / переменные

| Имя | Тип | Назначение |
| --- | --- | --- |
| `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` | secret | `deploy-user` для AWS / ECR / Terraform |
| `SSH_PRIVATE_KEY` | secret | Приватная половина ключа (та же, что у прода). Публичная — в `infra-prod.yml` / `preview.yml` (env `PREVIEW_SSH_PUBLIC_KEY`) |
| `PROD_ENV_FILE` | secret | Содержимое `.env.prod` (БД, OAUTH, TTL); reuse'ится для preview |
| `GH_PAT` | secret | Чтение submodules в build-фазе |
| `GITHUB_TOKEN` | встроенный | Sticky-комментарии в PR (`pull-requests: write`) |
| `AWS_REGION`, `VITE_API_BASE_URL` | vars | Регион + base-URL фронта |

Права `deploy-user` — все необходимые выданы (S3/DynamoDB опционально, в
коде используется S3 + native locking; `ec2:TerminateInstances` /
`DeleteSecurityGroup` нужны для teardown).

## Грабли (на чём напоролись при внедрении)

| Симптом | Причина | Лечение |
| --- | --- | --- |
| `403 Forbidden` на `HeadObject .../terraform.tfstate` | Имя бакета не по конвенции курса — IAM-политика `deploy-user` даёт S3 только на `dmc-1-t2-notebook-terraform-state` | Назвать бакет по конвенции |
| `terraform init`: `S3 bucket … does not exist` | На первом push'е `infra-prod` стартует параллельно с `infra-bootstrap` (race) | Перезапустить `infra-prod` после того, как bootstrap создал бакет |
| План прода хочет `destroy+create` SG (`# forces replacement`) | `description` у `aws_security_group` immutable; код не совпал с легаси-SG | Держать `description` ровно как у легаси (`"jsnotes-t2 prod: SSH + HTTP"`) |
| `Error acquiring the state lock` | Прошлый `apply` отменили на полпути → завис lock-объект | Удалить `…/terraform.tfstate.tflock` из S3 (или `terraform force-unlock`) |
| `env file ./.env.prod not found` на `compose config` | `env_file: ./.env.prod` ищет файл рядом с compose | Писать `.env.prod` в корень репо |

## Откатиться к старому (если что-то сломалось)

Прежняя императивная версия `infra-prod.yml` сохранена в истории git
(до коммита, добавляющего Terraform). Откат — `git revert` + удалить
ресурсы из state перед повторным запуском. **Не делать `terraform destroy`
на проде** без явного решения — это сломает работающий сайт.
