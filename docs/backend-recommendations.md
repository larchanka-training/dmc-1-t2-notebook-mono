# Backend Recommendations

Документ описывает рекомендуемый backend-стек для JS Notebook: приложения в стиле Jupyter Notebook для JavaScript/TypeScript с аккаунтами, офлайн-режимом, ручной синхронизацией, хранением notebook-данных и LLM-прокси.

## Цели Backend

Backend нужен не для выполнения JavaScript-кода. Код должен выполняться в браузере в sandbox/runtime слое frontend. Backend отвечает за:

- регистрацию, вход, сессии и авторизацию;
- хранение notebook-данных и истории синхронизации;
- ручную синхронизацию между IndexedDB и сервером;
- LLM-прокси, чтобы API-ключи не попадали в браузер;
- rate limiting, audit logs и базовую SaaS-инфраструктуру;
- OpenAPI-документацию для frontend-команды.

## Рекомендуемый MVP-стек

| Область | Технология | Для чего нужна | Ресурс |
| --- | --- | --- | --- |
| Runtime | Python 3.12+ | Единая версия для локальной разработки, Docker и CI | https://docs.python.org/3.12/ |
| Web framework | FastAPI `>=0.136.1,<0.137.0` | REST API, OpenAPI schema, dependency injection, async handlers, WebSocket/SSE | https://fastapi.tiangolo.com/ |
| ASGI server | Uvicorn `>=0.47.0,<0.48.0` | Production/dev запуск FastAPI-приложения | https://www.uvicorn.org/ |
| Validation | Pydantic `>=2.13.4,<3.0.0` | DTO, request/response schemas, сериализация и валидация | https://docs.pydantic.dev/ |
| Settings | Pydantic Settings `>=2.14.1,<3.0.0` | Типизированная конфигурация из env и `.env` | https://docs.pydantic.dev/latest/concepts/pydantic_settings/ |
| Database | PostgreSQL | Пользователи, notebooks, sync state, JSONB snapshots | https://www.postgresql.org/docs/ |
| ORM | SQLAlchemy 2.0 async | Async DB layer, модели, транзакции, контроль SQL | https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html |
| DB driver | asyncpg | Быстрый async PostgreSQL driver для SQLAlchemy | https://magicstack.github.io/asyncpg/current/ |
| Migrations | Alembic | Версионирование схемы БД | https://alembic.sqlalchemy.org/en/latest/ |
| Tests | Pytest | Unit/integration тесты backend | https://docs.pytest.org/ |
| HTTP client | HTTPX | Async-запросы к LLM providers и внешним API | https://www.python-httpx.org/ |

## Почему FastAPI

FastAPI уже подходит под текущий template и хорошо ложится на задачу:

- автоматически генерирует OpenAPI-документацию для frontend;
- работает поверх ASGI, Starlette и Pydantic;
- поддерживает async endpoints;
- имеет встроенную модель dependencies для auth, DB session и permission checks;
- подходит для REST API, WebSocket и streaming-сценариев.

Стабильная рекомендация для проекта: `fastapi>=0.136.1,<0.137.0`. Это близко к актуальной версии и ограничивает диапазон, чтобы CI не подтягивал случайный future-major/minor с несовместимыми изменениями.

## Данные и формат Notebook

Для MVP лучше использовать PostgreSQL как основной серверный источник данных, а IndexedDB оставить локальным offline-source на frontend.

| Сущность | Что хранит |
| --- | --- |
| `users` | аккаунты пользователей |
| `sessions` | refresh/session tokens, logout/revoke, устройства |
| `notebooks` | metadata notebook: owner, title, version, timestamps |
| `notebook_cells` | cells: text/code, content, order, metadata |
| `sync_events` | история ручной синхронизации, client id, base version |
| `llm_requests` | audit LLM-запросов: user, model, latency, status, tokens |

Для первой версии можно хранить notebook и cells нормализованно в таблицах. Если понадобится гибкость, часть metadata/output можно хранить в PostgreSQL `JSONB`.

## Синхронизация

Frontend хранит рабочую копию в IndexedDB, а backend принимает sync-запросы вручную.

MVP-стратегия:

- у каждого notebook есть `version` или `updated_at`;
- клиент отправляет `base_version` и локальные изменения;
- backend принимает изменения, если версия актуальна;
- если версия устарела, backend возвращает `409 Conflict`;
- на первом этапе conflict можно решать через Last-Write-Wins на уровне cell;
- позже добавить diff UI или CRDT.

Полезные технологии для следующих этапов:

| Технология | Для чего нужна | Ресурс |
| --- | --- | --- |
| Yjs | CRDT для совместного редактирования и conflict-free sync | https://docs.yjs.dev/ |
| y-py | Python bindings для Yjs, если CRDT потребуется на backend | https://github.com/y-crdt/ypy |
| WebSocket | Live-синхронизация и совместное редактирование в будущем | https://fastapi.tiangolo.com/advanced/websockets/ |
| Server-Sent Events | Односторонний streaming статусов или LLM-output | https://developer.mozilla.org/en-US/docs/Web/API/Server-sent_events |

## Auth и Session

Для MVP достаточно email/password + JWT access token + refresh/session token.

| Технология | Для чего нужна | Ресурс |
| --- | --- | --- |
| pwdlib | Password hashing, современная альтернатива ручной работе с bcrypt | https://github.com/frankie567/pwdlib |
| PyJWT | Создание и проверка JWT | https://pyjwt.readthedocs.io/ |
| python-jose | Альтернатива для JWT/JWS/JWE, если понадобится JOSE-экосистема | https://python-jose.readthedocs.io/ |
| Authlib | OAuth client/server, когда появится GitHub/Google login | https://docs.authlib.org/ |
| FastAPI security guide | Базовый пример OAuth2/JWT в FastAPI | https://fastapi.tiangolo.com/tutorial/security/oauth2-jwt/ |

Минимальная модель session:

- access token живет недолго;
- refresh/session token хранится в БД только в виде hash;
- `sessions` содержит `user_id`, `token_hash`, `expires_at`, `revoked_at`, `user_agent`, `ip`;
- logout помечает session как revoked;
- protected endpoints используют dependency `get_current_user`.

## LLM Proxy

LLM-запросы должны идти через backend, потому что browser не должен видеть API keys.

| Технология | Для чего нужна | Ресурс |
| --- | --- | --- |
| HTTPX | Async HTTP client для LLM provider API | https://www.python-httpx.org/ |
| OpenAI API | Один из возможных LLM providers | https://platform.openai.com/docs |
| Anthropic API | Альтернативный LLM provider | https://docs.anthropic.com/ |
| AWS Bedrock | Managed LLM provider в AWS, если команда выберет AWS | https://docs.aws.amazon.com/bedrock/ |
| Redis | Rate limiting, cache, queues | https://redis.io/docs/latest/ |
| slowapi | Rate limiting middleware для Starlette/FastAPI | https://slowapi.readthedocs.io/ |

Рекомендуемая внутренняя абстракция:

```text
LLMProvider
  generate_code(prompt, context) -> GeneratedCode

Providers:
  OpenAIProvider
  AnthropicProvider
  BedrockProvider
```

Так frontend работает с одним endpoint, а backend может менять provider через env/config.

## Background Jobs

На старте можно использовать FastAPI `BackgroundTasks` только для коротких задач. Для долгих или повторяемых задач лучше вынести worker.

| Технология | Для чего нужна | Ресурс |
| --- | --- | --- |
| FastAPI BackgroundTasks | Простые фоновые действия после ответа | https://fastapi.tiangolo.com/tutorial/background-tasks/ |
| Celery | Очереди задач, retries, scheduled jobs | https://docs.celeryq.dev/ |
| Dramatiq | Более простая альтернатива Celery | https://dramatiq.io/ |
| RQ | Простая очередь задач поверх Redis | https://python-rq.org/ |

Для проекта worker может понадобиться для:

- повторной синхронизации;
- тяжелых LLM-запросов;
- обработки exports;
- расчета notebook previews;
- email/notification tasks.

## Observability

| Технология | Для чего нужна | Ресурс |
| --- | --- | --- |
| structlog | Структурированные JSON logs | https://www.structlog.org/ |
| Loguru | Простое удобное логирование для небольших проектов | https://loguru.readthedocs.io/ |
| OpenTelemetry | Tracing/metrics/logs для распределенной системы | https://opentelemetry.io/docs/languages/python/ |
| Sentry | Error tracking | https://docs.sentry.io/platforms/python/ |

Для MVP достаточно structured logs + request id. OpenTelemetry и Sentry можно подключать позже.

## Testing

| Технология | Для чего нужна | Ресурс |
| --- | --- | --- |
| Pytest | Основной test runner | https://docs.pytest.org/ |
| pytest-asyncio | Async unit/integration tests | https://pytest-asyncio.readthedocs.io/ |
| HTTPX AsyncClient | Тестирование async API без реального HTTP-сервера | https://www.python-httpx.org/async/ |
| Testcontainers | Интеграционные тесты с реальным PostgreSQL/Redis в Docker | https://testcontainers-python.readthedocs.io/ |
| Ruff | Lint/format для Python | https://docs.astral.sh/ruff/ |
| Mypy | Static type checking | https://mypy.readthedocs.io/ |

Минимальный backend CI:

1. `ruff check .`
2. `pytest`
3. `docker build`

Следующий уровень:

1. `ruff format --check .`
2. `mypy app`
3. integration tests with PostgreSQL service.

## Deployment

| Технология | Для чего нужна | Ресурс |
| --- | --- | --- |
| Docker | Единый runtime для local/CI/deploy | https://docs.docker.com/ |
| Docker Compose | Локальная связка frontend/backend/postgres/proxy | https://docs.docker.com/compose/ |
| Nginx | Reverse proxy, HTTPS termination локально/на сервере | https://nginx.org/en/docs/ |
| GitHub Actions | CI pipeline: lint/test/build | https://docs.github.com/en/actions |

Для production позже стоит добавить:

- отдельный image registry;
- migration step перед запуском app;
- healthcheck endpoint;
- secrets management;
- backup policy для PostgreSQL.

## Предлагаемая структура Backend

```text
app/
  api/
    deps.py
    v1/
      endpoints/
        auth.py
        users.py
        notebooks.py
        sync.py
        llm.py
        health.py
      router.py
  core/
    config.py
    security.py
    logging.py
  db/
    base.py
    session.py
    migrations/
  models/
    user.py
    notebook.py
    session.py
    sync_event.py
    llm_request.py
  schemas/
    auth.py
    notebook.py
    sync.py
    llm.py
  repositories/
    user_repository.py
    notebook_repository.py
  services/
    auth_service.py
    notebook_service.py
    sync_service.py
    llm_service.py
  tests/
```

## Рекомендуемая последовательность внедрения

1. Зафиксировать Python 3.12, FastAPI, Pydantic, Uvicorn, pytest, ruff.
2. Добавить PostgreSQL + SQLAlchemy async + Alembic.
3. Добавить users/auth/sessions.
4. Добавить notebooks/cells CRUD.
5. Добавить ручную sync endpoint-модель.
6. Добавить LLM proxy с одним provider.
7. Добавить rate limiting и audit LLM-запросов.
8. Добавить интеграционные тесты с PostgreSQL.
