# CI в submodule `ui/` и его связь с CI монорепо

> Документ объясняет, что должен делать `ui/.github/workflows/pull-request.yml`
> внутри submodule-репозитория `dmc-1-t2-notebook-ui`, чем он отличается от
> `.github/workflows/ui-ci.yml` в монорепо `dmc-1-t2-notebook-mono`, и как они
> работают вместе. Аналогичная логика — для submodule `api/`.

---

## 1. Две точки входа CI: где живёт workflow

У нас есть **три** независимых GitHub-репозитория:

| Репозиторий | Роль | Где лежат его workflow-ы |
|---|---|---|
| `dmc-1-t2-notebook-mono` | Монорепо. Хранит `docker-compose.yaml`, submodule-указатели, общую инфраструктуру | `.github/workflows/*.yml` в моно |
| `dmc-1-t2-notebook-ui` | Чистый UI-репозиторий (тот же код, что в папке `ui/` монорепо через git submodule) | `ui/.github/workflows/*.yml` (это содержимое submodule-репо) |
| `dmc-1-t2-notebook-api` | Чистый API-репозиторий | `api/.github/workflows/*.yml` |

Каждый репозиторий **запускает свои собственные workflow-ы независимо**.
GitHub Actions знает только о workflow того репозитория, в котором произошло
событие.

---

## 2. Что когда триггерится

| Событие | Какой репозиторий | Какие workflow запускаются |
|---|---|---|
| PR в `dmc-1-t2-notebook-ui` (фича/баг во frontend) | UI-репо | `ui/.github/workflows/pull-request.yml` |
| Merge в `main` UI-репо | UI-репо | те же + любые release-workflow |
| PR в монорепо, который двигает submodule-pointer `ui` | Mono | `.github/workflows/ui-ci.yml` + `docker-compose-ci.yml` |
| PR в монорепо с правкой `docker-compose.yaml` | Mono | `docker-compose-ci.yml` |
| PR в `dmc-1-t2-notebook-api` | API-репо | `api/.github/workflows/...` |
| PR в монорепо, который двигает submodule-pointer `api` | Mono | `.github/workflows/api-ci.yml` + `docker-compose-ci.yml` |

Вывод: **PR во frontend сначала проходит CI UI-репо**, и только после merge
кто-то (или Dependabot/скрипт/руками) обновляет указатель submodule в
монорепо — это уже отдельный PR, который проверяется CI монорепо.

---

## 3. Зачем нужны два уровня CI

Может показаться, что это дублирование. На самом деле — нет.

| Уровень | Что проверяет | Что НЕ может проверить |
|---|---|---|
| CI **submodule** (`ui` репо) | Изоляция: «UI собирается и проходит тесты сам по себе» — lint, typecheck, unit-тесты, build, опционально storybook | Не знает про backend API, docker-compose, proxy, postgres. Не может протестировать end-to-end вместе с API |
| CI **монорепо** (`ui-ci.yml` в mono) | Интеграция: «текущий зафиксированный коммит UI собирается в Docker», и в перспективе — «весь стек поднимается через docker-compose, /health возвращает 200» | Не знает про in-progress ветки UI до их merge в `main` UI-репо |

То есть **UI-репо отвечает за качество UI**, **монорепо отвечает за то, что
все части собираются вместе**.

---

## 4. Текущее состояние `ui/.github/workflows/pull-request.yml`

Что сейчас (фрагмент):

```yaml
jobs:
  Lint:
    permissions: { contents: write }
    steps:
      - uses: actions/checkout@... { ref: ${{ github.head_ref }} }
      # - run: ./gradlew ktlintFormat   ← закомментировано
      - uses: stefanzweifel/git-auto-commit-action@... { commit_message: Auto format }
  Test:
    steps: [ checkout ]   # пусто
  Build:
    steps: [ checkout ]   # пусто
```

Проблемы:

1. **Lint** ничего не линтит — есть только `git-auto-commit-action`,
   который коммитит «изменения после форматирования», которых нет.
2. **Test** и **Build** — пустые заглушки.
3. `permissions: contents: write` без причины — нарушение принципа least
   privilege.
4. Workflow ссылается на `ktlintFormat` (это Kotlin/Gradle) — следы
   шаблона, не имеющего отношения к React/Vite.
5. Нет `concurrency`, нет кеша pnpm, нет typecheck.

---

## 5. Что должно быть в `ui/.github/workflows/pull-request.yml`

Минимально достаточный набор для UI-репо:

```yaml
name: UI Pull Request

on:
  pull_request:
    branches: [main]
  push:
    branches: [main]
  workflow_dispatch:

concurrency:
  group: ui-pr-${{ github.ref }}
  cancel-in-progress: true

permissions:
  contents: read          # читать код достаточно
  pull-requests: write    # если бот будет писать комментарии coverage/size

jobs:
  lint-and-typecheck:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@<pinned-sha>
        with: { persist-credentials: false }

      - uses: pnpm/action-setup@<pinned-sha>
        with: { version: 9.15.9 }

      - uses: actions/setup-node@<pinned-sha>
        with:
          node-version: '20'
          cache: pnpm
          cache-dependency-path: pnpm-lock.yaml

      - run: pnpm install --frozen-lockfile
      - run: pnpm run lint
      - run: pnpm run typecheck      # tsc -b
      - run: pnpm run format:check   # prettier --check

  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@<pinned-sha>
      - uses: pnpm/action-setup@<pinned-sha>
        with: { version: 9.15.9 }
      - uses: actions/setup-node@<pinned-sha>
        with: { node-version: '20', cache: pnpm, cache-dependency-path: pnpm-lock.yaml }
      - run: pnpm install --frozen-lockfile
      - run: pnpm test -- --coverage
      - uses: actions/upload-artifact@<pinned-sha>
        with: { name: coverage, path: coverage/ }

  build:
    runs-on: ubuntu-latest
    needs: [lint-and-typecheck, test]
    steps:
      - uses: actions/checkout@<pinned-sha>
      - uses: pnpm/action-setup@<pinned-sha>
        with: { version: 9.15.9 }
      - uses: actions/setup-node@<pinned-sha>
        with: { node-version: '20', cache: pnpm, cache-dependency-path: pnpm-lock.yaml }
      - run: pnpm install --frozen-lockfile
      - run: pnpm run build
      - uses: actions/upload-artifact@<pinned-sha>
        with: { name: ui-dist, path: dist/ }

  api-contract:
    name: OpenAPI contract drift
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@<pinned-sha>
      - uses: pnpm/action-setup@<pinned-sha>
        with: { version: 9.15.9 }
      - uses: actions/setup-node@<pinned-sha>
        with: { node-version: '20', cache: pnpm, cache-dependency-path: pnpm-lock.yaml }
      - run: pnpm install --frozen-lockfile
      - run: pnpm run api:check   # должен упасть, если openapi-типы расходятся
```

Зачем каждый job:

| Job | Зачем |
|---|---|
| `lint-and-typecheck` | Гарантирует отсутствие ошибок ESLint, TypeScript, Prettier. Самый быстрый — падает первым |
| `test` | Vitest + Testing Library + MSW. Без него можно сломать `notebook.test.ts`, `auth.test.ts` и не заметить |
| `build` | Vite-сборка. Ловит ошибки, которые проходят eslint/tsc, но падают на сборке (например, динамические импорты несуществующих файлов) |
| `api-contract` | `pnpm run api:check` — проверяет, что сгенерированные из OpenAPI типы соответствуют свежей схеме. Защита от рассинхрона UI ↔ API |

Что **убрать**:

- `git-auto-commit-action` в CI — авто-коммитов от CI лучше избегать,
  они мешают review и могут запускать бесконечный цикл workflow.
  Форматирование пусть делает локальный `lefthook` (уже подключён в `ui/`).
- `permissions: contents: write` — не нужно для read-only CI.

---

## 6. Как соотносится с `.github/workflows/ui-ci.yml` в монорепо

`ui-ci.yml` в моно делает:

```
lint (eslint) → build (vite) → docker-build (--target production)
```

То есть это **подмножество** того, что должно быть в `ui` submodule CI,
плюс Docker-сборка, которую submodule CI не делает (у submodule нет
`docker-compose.yaml`).

Логика разделения ответственности:

| Проверка | UI-репо (submodule CI) | Mono (`ui-ci.yml`) |
|---|---|---|
| ESLint | ✅ (быстрая, при каждом PR в UI) | ✅ (дублируется на всякий случай при обновлении pointer) |
| TypeScript typecheck | ✅ | желательно ✅ |
| Prettier check | ✅ | необязательно |
| Vitest | ✅ | желательно ✅ |
| Vite build | ✅ | ✅ |
| OpenAPI contract drift | ✅ | необязательно (это забота UI-команды) |
| Docker build UI-образа | ❌ (у submodule нет Dockerfile-страт. контекста с pinned API base url из моно) | ✅ |
| Docker compose up + smoke `/health` | ❌ | ✅ (когда добавим) |

Дублирование `lint/build` в обоих местах — это **намеренно**. Без него можно
сделать `git push --force` в submodule после прохождения mono-CI, и проверки
никто бы заново не запустил.

---

## 7. Поток работы (end-to-end)

Сценарий: разработчик добавляет фичу во frontend.

```
1. Branch feat/notebook-tabs в репо dmc-1-t2-notebook-ui
2. Push → PR в main UI-репо
   → срабатывает ui/.github/workflows/pull-request.yml
   → lint, typecheck, test, build
   → если зелёный — Review → Merge в main UI

3. Merge в main UI создаёт новый commit SHA, но
   монорепо его пока не «видит» — submodule pointer
   указывает на старый коммит

4. Кто-то (человек или Dependabot для submodules) делает в моно:
   git -C ui pull --ff-only
   git add ui
   git commit -m "chore: bump ui submodule to <SHA>"
   git push (PR)
   → срабатывает .github/workflows/ui-ci.yml
   → lint, build, docker build UI-образа
   → срабатывает docker-compose-ci.yml (если включён)
   → если зелёный — Review → Merge в main mono

5. (Будущее) Merge в main mono триггерит публикацию
   ghcr.io/<org>/js-notebook-ui:sha-<short> и :main
   → deploy job катит образ на staging/production
```

---

## 8. Чек-лист для UI-submodule

- [ ] Удалить `git-auto-commit-action` из CI.
- [ ] Добавить реальные шаги lint + typecheck + test + build.
- [ ] Закешировать pnpm через `actions/setup-node` (cache: pnpm).
- [ ] Запинить все actions по SHA, как уже сделано в моно.
- [ ] Добавить `concurrency` (отменять предыдущие билды на той же PR-ветке).
- [ ] `permissions: contents: read` (минимум).
- [ ] Опционально: `pnpm run api:check` для контроля контракта.
- [ ] Опционально: upload-artifact для `dist/` и `coverage/`.
- [ ] Опционально: bundle-size check (`size-limit` или `nx-style`).
- [ ] Включить required status checks в repository rules UI-репо.

---

## 9. Симметрия для `api/`

Аналогичная структура должна быть в `dmc-1-t2-notebook-api`:

| Job | Команда |
|---|---|
| `lint` | `ruff check .` |
| `format-check` | `ruff format --check .` |
| `typecheck` (когда добавим `mypy`/`pyright`) | `mypy app` |
| `test` | `pytest --cov=app` |
| (опц.) `migrations-check` (когда появится Alembic) | `alembic check` |

Mono `api-ci.yml` дополняет это сборкой Docker-образа и в будущем — smoke-тестом
через docker-compose.

---

## 10. TL;DR

- `ui/.github/workflows/pull-request.yml` сейчас почти пустой и проверяет
  ровно ноль кода UI.
- Он должен содержать **четыре** реальных job: lint+typecheck, test, build
  и OpenAPI contract check.
- Mono-workflow `.github/workflows/ui-ci.yml` его не заменяет: он
  отвечает за «UI собирается в Docker внутри монорепо», а submodule CI —
  за «UI вообще валиден сам по себе».
- Эти два уровня **дополняют** друг друга, а не дублируют без смысла.
