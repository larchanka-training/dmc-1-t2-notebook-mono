# GitHub Actions PR Checks

Документ объясняет, как команда использует GitHub Actions в pull requests, как читать статусы checks и когда PR можно merge.

## Что такое PR checks

Когда создаётся pull request в `main`, GitHub запускает workflow из `.github/workflows/`.

Per-module lint/tests живут в CI самих сабмодулей (репозитории `api`/`ui`),
а не в monorepo. В monorepo на PR работает интеграционная проверка:

| Workflow | Файл | Когда запускается | Что проверяет |
| --- | --- | --- | --- |
| Docker Compose CI | `.github/workflows/docker-compose-ci.yml` | PR в `main`, если изменились `api`/`ui` (вкл. bump сабмодуля), `proxy/**`, compose или сам workflow | поднимает весь стек (api+ui+postgres+proxy) и гоняет smoke-тесты |

Публикация образов (`ecr-publish.yml`) на PR не запускается — только на push в `main` или теге `v*.*.*`. Если PR меняет только документацию вне runtime-путей, Docker Compose CI может не запуститься из-за `paths` filter.

## Как работает CI в нашем monorepo

В CI GitHub runner сначала клонирует monorepo, потом подтягивает private submodules:

- `api`
- `ui`

Для этого используется repository secret `GH_PAT`. Сабмодули подтягиваются
**отдельным шагом** (а не через `actions/checkout`):

```yaml
- name: Checkout submodules
  run: |
    git config --global url."https://${{ secrets.GH_PAT }}@github.com/".insteadOf "https://github.com/"
    git submodule update --init --recursive
```

Если `GH_PAT` не имеет доступа к private submodules, CI падает на этом шаге.

Типовая ошибка:

```text
fatal: unable to access '...dmc-1-t2-notebook-api.git/': The requested URL returned error: 403
remote: Write access to repository not granted.
```

Если шаг `Checkout submodules` зелёный, значит token работает и CI дошёл до реальных проверок проекта.

## Какие проверки должны пройти

Per-module проверки живут в CI самих сабмодулей (`api`/`ui`), не в monorepo.
Docker-образы собираются на уровне monorepo: `docker compose build` на PR
(`docker-compose-ci.yml`), а публикация — на `main` (`ecr-publish.yml` →
`build-images.yml`). Отдельного per-submodule «Docker Build» job нет.

### API CI (`api/.github/workflows/pull-request.yml`)

| Job | Что делает | Что означает failure |
| --- | --- | --- |
| `Lint` | `ruff check .` | Ошибка стиля/импорта/линта |
| `Unit tests` | `pytest` | Сломан backend behavior или тесты |
| `CI complete` | гейт: все джобы выше прошли | Что-то из lint/test упало/отменено |

### UI CI (`ui/.github/workflows/pull-request.yml`)

| Job | Что делает | Что означает failure |
| --- | --- | --- |
| `Lint` | `format:check` + ESLint | Ошибка форматирования/линта |
| `Unit tests` | `test:coverage` (Vitest) + coverage-отчёт | Сломаны frontend-тесты |
| `Build` | `pnpm run build` (production build) | Ошибка TypeScript/Vite/сборки |
| `CI complete` | гейт: все джобы выше прошли | Что-то упало/отменено |

## Когда PR можно merge

PR можно merge, когда выполнены все условия:

1. Нет merge conflicts.
2. Все relevant checks зелёные.
3. Review/approval соответствует правилам команды.
4. В PR нет незавершённых discussion threads.
5. Если PR обновляет submodule pointer, commit в submodule уже запушен и доступен в remote repo.

Важно: зелёный CI не заменяет review. CI проверяет автоматические сценарии, но не проверяет архитектурные решения, полноту требований и корректность бизнес-логики.

## Как читать статус PR

В нижней части PR GitHub показывает checks.

| Статус | Значение | Что делать |
| --- | --- | --- |
| Green / success | Проверка прошла | Можно переходить к review/merge |
| Red / failure | Проверка упала | Открыть failed job и смотреть первый meaningful error |
| Yellow / pending | Проверка ещё идёт | Дождаться завершения |
| Skipped | Workflow/job не запускался по условиям | Проверить, ожидаемо ли это для текущего PR |

## Как смотреть логи через GitHub UI

1. Открыть PR.
2. Внизу найти блок checks.
3. Нажать `Details` у нужного workflow.
4. Открыть failed job.
5. Найти первый шаг с ошибкой.

Обычно смотреть нужно не последний stack trace, а первый шаг, где появилась реальная причина.

## Как смотреть логи через GitHub CLI

Список последних runs:

```bash
gh run list --repo larchanka-training/dmc-1-t2-notebook-mono --limit 10
```

Посмотреть детали run:

```bash
gh run view <RUN_ID> --repo larchanka-training/dmc-1-t2-notebook-mono
```

Посмотреть failed logs:

```bash
gh run view <RUN_ID> --repo larchanka-training/dmc-1-t2-notebook-mono --log-failed
```

Проверить checks конкретного PR:

```bash
gh pr checks <PR_NUMBER> --repo larchanka-training/dmc-1-t2-notebook-mono
```

## Типовые проблемы

### Checkout submodules падает

Причина обычно в `GH_PAT`.

Проверить:

- secret `GH_PAT` существует в monorepo settings;
- token approved в организации;
- token имеет доступ к `dmc-1-t2-notebook-mono`, `dmc-1-t2-notebook-api`, `dmc-1-t2-notebook-ui`;
- token имеет минимум read-доступ к contents private repositories.

### Lint падает

Запустить локально соответствующую команду:

```bash
cd api
ruff check .
```

или:

```bash
cd ui
pnpm run lint
```

### Tests падают

Запустить локально:

```bash
cd api
pytest
```

или для UI, когда тесты будут настроены:

```bash
cd ui
pnpm test
```

### Docker Build падает

Запустить локально из корня monorepo:

```bash
docker build -t js-notebook-api:local ./api
docker build --target production -t js-notebook-ui:local ./ui
```

Если локально проходит, а в GitHub Actions падает, проверить разницу env, secrets, network и base image.

## Как использовать в рабочем процессе

Рекомендуемый порядок для PR:

1. Создать ветку.
2. Сделать изменения.
3. Проверить локально минимальные команды.
4. Push branch.
5. Создать PR.
6. Дождаться GitHub Actions.
7. Если checks red, исправить и push новый commit.
8. Если checks green, запросить review.
9. После approval и отсутствия conflicts выполнить merge.
10. После merge удалить feature branch.

## Полезные ссылки

- GitHub Actions workflow syntax: https://docs.github.com/actions/reference/workflows-and-actions/workflow-syntax
- Events that trigger workflows: https://docs.github.com/actions/learn-github-actions/events-that-trigger-workflows
- Troubleshooting required status checks: https://docs.github.com/en/pull-requests/collaborating-with-pull-requests/collaborating-on-repositories-with-code-quality-features/troubleshooting-required-status-checks
- Protected branches and required checks: https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-protected-branches/about-protected-branches
