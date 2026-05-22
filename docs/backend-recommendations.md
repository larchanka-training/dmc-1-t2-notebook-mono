# Backend Recommendations

This document describes the recommended backend stack for JS Notebook: a Jupyter Notebook-style application for JavaScript/TypeScript with accounts, offline mode, manual synchronization, notebook data storage, and an LLM proxy.

## Backend Goals

The primary path for executing JavaScript code is browser-based (QuickJS/WASM in
the frontend sandbox/runtime layer). The backend acts as a **fallback executor**:
when the client's RAM is ≤ 4 GB or for a resource-intensive request, the code is executed on the server
(see `execution-architecture.md`). In addition, the backend is responsible for:

- registration, login, sessions, and authorization;
- fallback code execution in the server-side QuickJS sandbox;
- storing notebook data and synchronization history;
- manual synchronization between IndexedDB and the server;
- the LLM proxy, so that API keys do not reach the browser;
- rate limiting, audit logs, and the basic SaaS infrastructure;
- OpenAPI documentation for the frontend team.

## Recommended MVP Stack

| Area | Technology | What it is for | Resource |
| --- | --- | --- | --- |
| Runtime | Python 3.12+ | A single version for local development, Docker, and CI | https://docs.python.org/3.12/ |
| Web framework | FastAPI `>=0.136.1,<0.137.0` | REST API, OpenAPI schema, dependency injection, async handlers, WebSocket/SSE | https://fastapi.tiangolo.com/ |
| ASGI server | Uvicorn `>=0.47.0,<0.48.0` | Production/dev launch of the FastAPI application | https://www.uvicorn.org/ |
| Validation | Pydantic `>=2.13.4,<3.0.0` | DTO, request/response schemas, serialization and validation | https://docs.pydantic.dev/ |
| Settings | Pydantic Settings `>=2.14.1,<3.0.0` | Typed configuration from env and `.env` | https://docs.pydantic.dev/latest/concepts/pydantic_settings/ |
| Database | PostgreSQL | Users, notebooks, sync state, JSONB snapshots | https://www.postgresql.org/docs/ |
| ORM | SQLAlchemy 2.0 async | Async DB layer, models, transactions, SQL control | https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html |
| DB driver | asyncpg | A fast async PostgreSQL driver for SQLAlchemy | https://magicstack.github.io/asyncpg/current/ |
| Migrations | Alembic | DB schema versioning | https://alembic.sqlalchemy.org/en/latest/ |
| Tests | Pytest | Unit/integration tests for the backend | https://docs.pytest.org/ |
| HTTP client | HTTPX | Async requests to LLM providers and external APIs | https://www.python-httpx.org/ |

## Why FastAPI

FastAPI already fits the current template and maps well onto the task:

- it automatically generates OpenAPI documentation for the frontend;
- it runs on top of ASGI, Starlette, and Pydantic;
- it supports async endpoints;
- it has a built-in dependencies model for auth, DB sessions, and permission checks;
- it is suitable for REST API, WebSocket, and streaming scenarios.

A stable recommendation for the project: `fastapi>=0.136.1,<0.137.0`. This is close to the current version and constrains the range so that CI does not pull in a random future major/minor with incompatible changes.

## Data and Notebook Format

For the MVP, it is better to use PostgreSQL as the primary server-side data source, and to leave IndexedDB as the local offline source on the frontend.

| Entity | What it stores |
| --- | --- |
| `users` | user accounts |
| `sessions` | refresh/session tokens, logout/revoke, devices |
| `notebooks` | notebook metadata: owner, title, version, timestamps |
| `notebook_cells` | cells: text/code, content, order, metadata |
| `sync_events` | manual synchronization history, client id, base version |
| `llm_requests` | audit of LLM requests: user, model, latency, status, tokens |

For the first version, notebooks and cells can be stored in normalized tables. If flexibility is needed, part of the metadata/output can be stored in PostgreSQL `JSONB`.

## Synchronization

The frontend keeps a working copy in IndexedDB, and the backend accepts sync requests manually.

MVP strategy:

- each notebook has a `version` or `updated_at`;
- the client sends a `base_version` and local changes;
- the backend accepts the changes if the version is current;
- if the version is outdated, the backend returns `409 Conflict`;
- in the first stage, conflicts can be resolved via Last-Write-Wins at the cell level;
- later, add a diff UI or CRDT.

Useful technologies for the next stages:

| Technology | What it is for | Resource |
| --- | --- | --- |
| Yjs | CRDT for collaborative editing and conflict-free sync | https://docs.yjs.dev/ |
| y-py | Python bindings for Yjs, if CRDT is needed on the backend | https://github.com/y-crdt/ypy |
| WebSocket | Live synchronization and collaborative editing in the future | https://fastapi.tiangolo.com/advanced/websockets/ |
| Server-Sent Events | One-way streaming of statuses or LLM output | https://developer.mozilla.org/en-US/docs/Web/API/Server-sent_events |

## Auth and Session

For the MVP, email/password + a JWT access token + a refresh/session token is sufficient.

| Technology | What it is for | Resource |
| --- | --- | --- |
| pwdlib | Password hashing, a modern alternative to working with bcrypt manually | https://github.com/frankie567/pwdlib |
| PyJWT | Creating and verifying JWTs | https://pyjwt.readthedocs.io/ |
| python-jose | An alternative for JWT/JWS/JWE, if the JOSE ecosystem is needed | https://python-jose.readthedocs.io/ |
| Authlib | OAuth client/server, when GitHub/Google login is added | https://docs.authlib.org/ |
| FastAPI security guide | A basic example of OAuth2/JWT in FastAPI | https://fastapi.tiangolo.com/tutorial/security/oauth2-jwt/ |

Minimal session model:

- the access token is short-lived;
- the refresh/session token is stored in the DB only as a hash;
- `sessions` contains `user_id`, `token_hash`, `expires_at`, `revoked_at`, `user_agent`, `ip`;
- logout marks the session as revoked;
- protected endpoints use the `get_current_user` dependency.

## LLM Proxy

LLM requests must go through the backend, because the browser must not see the API keys.

| Technology | What it is for | Resource |
| --- | --- | --- |
| HTTPX | Async HTTP client for the LLM provider API | https://www.python-httpx.org/ |
| OpenAI API | One of the possible LLM providers | https://platform.openai.com/docs |
| Anthropic API | An alternative LLM provider | https://docs.anthropic.com/ |
| AWS Bedrock | A managed LLM provider in AWS, if the team chooses AWS | https://docs.aws.amazon.com/bedrock/ |
| Redis | Rate limiting, cache, queues | https://redis.io/docs/latest/ |
| slowapi | Rate limiting middleware for Starlette/FastAPI | https://slowapi.readthedocs.io/ |

Recommended internal abstraction:

```text
LLMProvider
  generate_code(prompt, context) -> GeneratedCode

Providers:
  OpenAIProvider
  AnthropicProvider
  BedrockProvider
```

This way the frontend works with a single endpoint, and the backend can switch the provider via env/config.

## Background Jobs

At the start, FastAPI `BackgroundTasks` can be used only for short tasks. For long or recurring tasks, it is better to move them out to a worker.

| Technology | What it is for | Resource |
| --- | --- | --- |
| FastAPI BackgroundTasks | Simple background actions after the response | https://fastapi.tiangolo.com/tutorial/background-tasks/ |
| Celery | Task queues, retries, scheduled jobs | https://docs.celeryq.dev/ |
| Dramatiq | A simpler alternative to Celery | https://dramatiq.io/ |
| RQ | A simple task queue on top of Redis | https://python-rq.org/ |

For this project, a worker may be needed for:

- re-synchronization;
- heavy LLM requests;
- processing exports;
- computing notebook previews;
- email/notification tasks.

## Observability

| Technology | What it is for | Resource |
| --- | --- | --- |
| structlog | Structured JSON logs | https://www.structlog.org/ |
| Loguru | Simple, convenient logging for small projects | https://loguru.readthedocs.io/ |
| OpenTelemetry | Tracing/metrics/logs for a distributed system | https://opentelemetry.io/docs/languages/python/ |
| Sentry | Error tracking | https://docs.sentry.io/platforms/python/ |

For the MVP, structured logs + a request id are sufficient. OpenTelemetry and Sentry can be added later.

## Testing

| Technology | What it is for | Resource |
| --- | --- | --- |
| Pytest | The main test runner | https://docs.pytest.org/ |
| pytest-asyncio | Async unit/integration tests | https://pytest-asyncio.readthedocs.io/ |
| HTTPX AsyncClient | Testing async APIs without a real HTTP server | https://www.python-httpx.org/async/ |
| Testcontainers | Integration tests with a real PostgreSQL/Redis in Docker | https://testcontainers-python.readthedocs.io/ |
| Ruff | Lint/format for Python | https://docs.astral.sh/ruff/ |
| Mypy | Static type checking | https://mypy.readthedocs.io/ |

Minimal backend CI:

1. `ruff check .`
2. `pytest`
3. `docker build`

Next level:

1. `ruff format --check .`
2. `mypy app`
3. integration tests with PostgreSQL service.

## Deployment

| Technology | What it is for | Resource |
| --- | --- | --- |
| Docker | A unified runtime for local/CI/deploy | https://docs.docker.com/ |
| Docker Compose | A local bundle of frontend/backend/postgres/proxy | https://docs.docker.com/compose/ |
| Nginx | Reverse proxy, HTTPS termination locally/on the server | https://nginx.org/en/docs/ |
| GitHub Actions | CI pipeline: lint/test/build | https://docs.github.com/en/actions |

For production, it is worth adding later:

- a separate image registry;
- a migration step before launching the app;
- a healthcheck endpoint;
- secrets management;
- a backup policy for PostgreSQL.

## Proposed Backend Structure

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

## Recommended Implementation Sequence

1. Pin Python 3.12, FastAPI, Pydantic, Uvicorn, pytest, ruff.
2. Add PostgreSQL + SQLAlchemy async + Alembic.
3. Add users/auth/sessions.
4. Add notebooks/cells CRUD.
5. Add the manual sync endpoint model.
6. Add the LLM proxy with one provider.
7. Add rate limiting and audit of LLM requests.
8. Add integration tests with PostgreSQL.
