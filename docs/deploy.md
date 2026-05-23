# Deploy Workflow

## Назначение

Deploy workflow выкатывает прод-окружение из Docker-образов, опубликованных в
Amazon ECR. Работает в двух режимах:

- **АВТО** — запускается автоматически после успешного `ECR Publish` на ветке
  `main` (это «автодеплой при merge в main»); деплоит тег `latest`.
- **РУЧНОЙ** (`workflow_dispatch`) — выбираешь тег; нужен для ОТКАТА на старый
  immutable `sha-<short>`. Окружение всегда `production` (staging пока нет).

На текущем этапе фактический деплой — dry-run: workflow проверяет окружение, tag
образа и валидность production Docker Compose конфигурации, но на сервер не
ходит (реальный выкат — terraform/ssh, помечен TODO в `deploy.yml`).

Файл workflow:

```text
.github/workflows/deploy.yml
```

Связанная задача:

```text
https://github.com/larchanka-training/dmc-1-t2-notebook-mono/issues/42
```

## Как запускать

**Авто:** ничего делать не нужно — после merge в `main` и успешного `ECR Publish`
деплой запускается сам (тег `latest`, окружение `production`). Если у окружения
`production` включены required reviewers, запуск ждёт ручного approval.

**Вручную** (откат или деплой конкретного тега): откройте GitHub Actions,
выберите `Deploy` → Run workflow.

Обязательные inputs (только для ручного режима):

| Input | Допустимые значения | Пример |
| --- | --- | --- |
| `image_tag` | tag из ECR без префикса `api-`/`ui-` | `latest`, `sha-8be47cc` |

Workflow использует:

```text
docker-compose.prod.yaml
.env.prod.example
```

Выбранный `image_tag` записывается во временный файл `.env.prod` во время
запуска workflow. Секреты в репозиторий не записываются.

## Что проверяет workflow

Текущий dry-run job проверяет:

- `image_tag` не пустой;
- `image_tag` похож на валидный Docker tag;
- команда `docker compose --env-file .env.prod -f docker-compose.prod.yaml config` завершается успешно;
- в GitHub Actions summary выводятся окружение (`production`) и Docker-образы.

Ожидаемые имена образов:

```text
867633231218.dkr.ecr.eu-north-1.amazonaws.com/jsnotes-t2:api-<image_tag>
867633231218.dkr.ecr.eu-north-1.amazonaws.com/jsnotes-t2:ui-<image_tag>
```

## GitHub Environments

Сейчас в проекте только одно окружение — `production` (staging пока нет).

```text
production
```

Рекомендация:

- `production`: включить required reviewers перед production deploy — тогда даже
  авто-деплой после merge будет ждать ручного approval.

Staging добавляется позже отдельной задачей: вернуть input `environment` в
`deploy.yml` и завести GitHub Environment `staging`.

Workflow job использует:

```yaml
environment: production
```

На это окружение можно повесить environment-specific secrets и required
reviewers. Staging добавляется позже (вернуть input `environment`).

## Будущие SSH Deploy Secrets

Когда появится реальный сервер, эти secrets нужно добавить в нужный GitHub
Environment, а не хранить как обычные переменные в коде:

| Secret | Назначение |
| --- | --- |
| `SSH_HOST` | hostname или IP-адрес сервера |
| `SSH_USER` | Linux user для деплоя |
| `SSH_PRIVATE_KEY` | private key для SSH-аутентификации |
| `AWS_ACCESS_KEY_ID` | ключ для `docker login` в ECR (предпочтительнее — IAM-роль инстанса) |
| `AWS_SECRET_ACCESS_KEY` | секрет к ключу выше |

Реальные значения secrets нельзя коммитить в git.

## Будущий SSH Deploy Flow

Когда сервер будет готов, deploy job можно расширить следующими шагами:

1. Подключиться к серверу по SSH.
2. Авторизоваться в ECR (токен живёт 12 часов; на сервере удобнее IAM-роль
   инстанса или `amazon-ecr-credential-helper`):

```bash
aws ecr get-login-password --region eu-north-1 \
  | docker login --username AWS --password-stdin 867633231218.dkr.ecr.eu-north-1.amazonaws.com
```

3. Скачать выбранные Docker-образы:

```bash
docker pull 867633231218.dkr.ecr.eu-north-1.amazonaws.com/jsnotes-t2:api-${IMAGE_TAG}
docker pull 867633231218.dkr.ecr.eu-north-1.amazonaws.com/jsnotes-t2:ui-${IMAGE_TAG}
```

4. Запустить production compose:

```bash
IMAGE_TAG=${IMAGE_TAG} docker compose --env-file .env.prod -f docker-compose.prod.yaml up -d
```

5. Выполнить smoke checks:

```bash
curl -fsS https://api.notebook.com/api/v1/health
curl -fsS https://notebook.com/
```

## Rollback

Rollback должен использовать тот же manual workflow, но с предыдущим immutable
image tag, например:

```text
sha-8be47cc
```

Для production rollback лучше не использовать mutable tags вроде `main`.

## Текущее ограничение

Этот workflow пока не деплоит приложение на реальный сервер. Он только проверяет
deploy inputs и production compose configuration.

SSH deploy нужно добавлять отдельным изменением, когда будут готовы:

- целевой сервер;
- домен;
- стратегия TLS;
- production secrets.
