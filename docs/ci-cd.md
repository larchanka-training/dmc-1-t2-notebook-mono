# Mono-repo DevOps notes

Этот репозиторий используется для локальной разработки и запуска всех сервисов через Docker Compose.

Per-module CI и его документация живут в репозиториях сабмодулей:

- `api/docs/ci-cd.md`
- `ui/docs/ci-cd.md`

api и ui **собираются и публикуются** как отдельные образы (`api-`/`ui-`), но
**деплоятся вместе** одним production-стеком (`docker-compose.prod.yaml`).

## Production Docker Compose

Production compose запускает готовые Docker images из Amazon ECR и не собирает
`api`/`ui` локально.

Перед запуском private images нужен login в ECR:

```bash
aws ecr get-login-password --region eu-north-1 \
  | docker login --username AWS --password-stdin 867633231218.dkr.ecr.eu-north-1.amazonaws.com
```

Подготовка env-файла:

```bash
cp .env.prod.example .env.prod
```

Перед production запуском замените `change-me` значения в
`.env.prod`. Для реального production используйте immutable tag:

```bash
IMAGE_TAG=sha-8be47cc
```

Запуск:

```bash
docker compose --env-file .env.prod -f docker-compose.prod.yaml pull
docker compose --env-file .env.prod -f docker-compose.prod.yaml up -d
docker compose --env-file .env.prod -f docker-compose.prod.yaml ps
```

Smoke-check:

```bash
curl http://localhost/api/v1/health
curl http://localhost/
```

Остановка:

```bash
docker compose --env-file .env.prod -f docker-compose.prod.yaml down
```
