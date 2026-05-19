# Ручной Deploy Workflow

## Назначение

Deploy workflow подготавливает проект к ручному деплою из Docker-образов,
опубликованных в GHCR.

На текущем этапе это dry-run workflow: он проверяет выбранное окружение, tag
образа и валидность production Docker Compose конфигурации, но не подключается к
серверу.

Файл workflow:

```text
.github/workflows/deploy.yml
```

Связанная задача:

```text
https://github.com/larchanka-training/dmc-1-t2-notebook-mono/issues/42
```

## Как запускать

Откройте GitHub Actions, выберите `Manual Deploy` и запустите workflow вручную.

Обязательные inputs:

| Input | Допустимые значения | Пример |
| --- | --- | --- |
| `environment` | `staging`, `production` | `staging` |
| `image_tag` | любой валидный Docker tag из GHCR | `main`, `sha-8be47cc` |

Workflow использует:

```text
docker-compose.prod.yaml
.env.prod.example
```

Выбранный `image_tag` записывается во временный файл `.env.prod` во время
запуска workflow. Секреты в репозиторий не записываются.

## Что проверяет workflow

Текущий dry-run job проверяет:

- `environment` равен `staging` или `production`;
- `image_tag` не пустой;
- `image_tag` похож на валидный Docker tag;
- команда `docker compose --env-file .env.prod -f docker-compose.prod.yaml config` завершается успешно;
- в GitHub Actions summary выводятся целевое окружение и Docker-образы.

Ожидаемые имена образов:

```text
ghcr.io/larchanka-training/js-notebook-api:<image_tag>
ghcr.io/larchanka-training/js-notebook-ui:<image_tag>
```

## GitHub Environments

В настройках репозитория должны быть созданы два GitHub Environments:

```text
staging
production
```

Рекомендуемые настройки:

- `staging`: без обязательных reviewers, используется для проверки deployment wiring;
- `production`: включить required reviewers перед выполнением production deploy.

Workflow job использует:

```yaml
environment: ${{ inputs.environment }}
```

Это позволяет позже добавить отдельные environment-specific secrets для
`staging` и `production`.

## Будущие SSH Deploy Secrets

Когда появится реальный сервер, эти secrets нужно добавить в нужный GitHub
Environment, а не хранить как обычные переменные в коде:

| Secret | Назначение |
| --- | --- |
| `SSH_HOST` | hostname или IP-адрес сервера |
| `SSH_USER` | Linux user для деплоя |
| `SSH_PRIVATE_KEY` | private key для SSH-аутентификации |
| `GHCR_USERNAME` | GitHub username или bot account для скачивания GHCR images |
| `GHCR_READ_TOKEN` | token с правом чтения private GHCR packages |

Реальные значения secrets нельзя коммитить в git.

## Будущий SSH Deploy Flow

Когда сервер будет готов, deploy job можно расширить следующими шагами:

1. Подключиться к серверу по SSH.
2. Авторизоваться в GHCR:

```bash
echo "${GHCR_READ_TOKEN}" | docker login ghcr.io -u "${GHCR_USERNAME}" --password-stdin
```

3. Скачать выбранные Docker-образы:

```bash
docker pull ghcr.io/larchanka-training/js-notebook-api:${IMAGE_TAG}
docker pull ghcr.io/larchanka-training/js-notebook-ui:${IMAGE_TAG}
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
