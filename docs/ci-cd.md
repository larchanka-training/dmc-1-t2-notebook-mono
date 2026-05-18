# Mono-repo DevOps notes

Этот репозиторий используется для локальной разработки и запуска всех сервисов через Docker Compose.

CI/CD и deployment-документация находятся внутри отдельных submodules:

- `api/docs/ci-cd.md`
- `ui/docs/ci-cd.md`

Frontend и Backend деплоятся отдельно.

## Production Docker Compose

Production compose запускает готовые Docker images из GHCR и не собирает
`api`/`ui` локально.

Перед запуском private images нужен login в GHCR:

```bash
gh auth token | docker login ghcr.io -u <github-username> --password-stdin
```

Подготовка env-файла:

```bash
cp .env.prod.example .env.prod
```

Перед shared/staging/production запуском замените `change-me` значения в
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
