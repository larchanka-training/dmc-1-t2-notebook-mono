# GitHub Actions PR Checks

Документ объясняет, как команда использует GitHub Actions в pull requests, как читать статусы checks и когда PR можно merge.

## Что такое PR checks

Когда создаётся pull request в `main`, GitHub запускает workflow из `.github/workflows/`.

В нашем monorepo есть два основных CI workflow:

| Workflow | Файл | Когда запускается | Что проверяет |
| --- | --- | --- | --- |
| API CI | `.github/workflows/api-ci.yml` | PR/push в `main`, если изменились `api/**` или сам workflow | backend lint, backend tests, Docker build API |
| UI CI | `.github/workflows/ui-ci.yml` | PR/push в `main`, если изменились `ui/**` или сам workflow | frontend lint, build, Docker build UI |

Если PR меняет только backend, может запуститься только `API CI`. Если PR меняет только документацию вне `api/**` и `ui/**`, эти workflow могут не запускаться из-за `paths` filter.

## Как работает CI в нашем monorepo

В CI GitHub runner сначала клонирует monorepo, потом подтягивает private submodules:

- `api`
- `ui`

Для этого используется repository secret:

```yaml
token: ${{ secrets.GH_PAT }}
submodules: recursive
```

Если `GH_PAT` не имеет доступа к private submodules, CI падает на checkout до запуска lint/test/build.

Типовая ошибка:

```text
fatal: unable to access '...dmc-1-t2-notebook-api.git/': The requested URL returned error: 403
remote: Write access to repository not granted.
```

Если шаг `Checkout submodules` зелёный, значит token работает и CI дошёл до реальных проверок проекта.

## Какие проверки должны пройти

### API CI

| Job | Что делает | Что означает failure |
| --- | --- | --- |
| `Lint` | Устанавливает Python-зависимости и запускает `ruff check .` | Ошибка стиля, импорта, неиспользуемого кода или ruff-конфигурации |
| `Test` | Устанавливает dev-зависимости и запускает `pytest` | Сломан backend behavior или тестовая конфигурация |
| `Docker Build` | Собирает Docker image из `api/Dockerfile` | Backend не собирается в production-like Docker runtime |

### UI CI

| Job | Что делает | Что означает failure |
| --- | --- | --- |
| `Lint` | Устанавливает pnpm-зависимости и запускает ESLint | Ошибка frontend lint |
| `Build` | Запускает production build UI | Ошибка TypeScript/Vite/build |
| `Docker Build` | Собирает Docker image из `ui/Dockerfile` | UI не собирается в Docker runtime |

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
