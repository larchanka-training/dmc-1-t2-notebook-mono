# GitHub Repository Settings

Документ описывает рекомендуемые настройки GitHub repositories для проекта JS Notebook. Его можно использовать как чеклист для monorepo и submodule repositories.

## Репозитории проекта

| Repository | Назначение |
| --- | --- |
| `dmc-1-t2-notebook-mono` | Monorepo, Docker Compose, CI workflows, общая документация, submodule pointers |
| `dmc-1-t2-notebook-api` | Backend FastAPI service |
| `dmc-1-t2-notebook-ui` | Frontend React/Vite service |

Сокращения:

- **FE** — фронтенд, сабмодуль/папка `ui`
- **BE** — бэкенд, сабмодуль/папка `api`

## Цели настроек

- Запретить случайные прямые изменения в `main`.
- Проводить изменения через pull request.
- Требовать успешные GitHub Actions checks перед merge.
- Защитить private submodules и secrets.
- Сделать процесс review одинаковым для всей команды.
- Автоматизировать обновления зависимостей через Dependabot.

## Branch Protection / Rulesets

Рекомендуется использовать GitHub Rulesets для ветки `main`.

Путь в GitHub UI:

```text
Repository -> Settings -> Rules -> Rulesets -> New ruleset
```

Рекомендуемые настройки:

| Setting | Рекомендация | Зачем |
| --- | --- | --- |
| Ruleset name | `Protect main` | Понятное имя правила |
| Enforcement status | `Active` | Правило реально применяется |
| Target branches | `main` | Защищаем основную ветку |
| Restrict deletions | Enabled | Запрет удаления `main` |
| Require linear history | Optional | Включать, если команда договорилась о squash/rebase |
| Require pull request | Enabled | Все изменения через PR |
| Required approvals | `1` | Минимум один review |
| Dismiss stale approvals | Recommended | Старый approval сбрасывается после новых commits |
| Require conversation resolution | Enabled | Нельзя merge с незакрытыми обсуждениями |
| Require status checks | Enabled | Нельзя merge с красным CI |
| Block force pushes | Enabled | Защита истории `main` |

## Required Status Checks

Для monorepo стоит требовать checks, которые соответствуют изменённой части проекта. При этом текущие workflow используют `paths` filters, поэтому их нельзя бездумно включать как глобальные required checks для каждого PR.

Текущие CI jobs:

| Workflow | Когда запускается | Делать required сейчас? | Комментарий |
| --- | --- | --- | --- |
| Docker Compose CI | PR (`api`/`ui`/`proxy`/compose) | Candidate, не global required | Интеграционный monorepo PR-gate; не появляется на docs-only PR |
| ECR Publish → Build & Push Images (reusable) | push `main` / тег `v*.*.*` / manual | Не required | На PR не запускается; публикует образы в ECR |
| Preview Environment | PR (`api`/`ui`/`proxy`/compose/`terraform`) | Не required | Собирает `pr-<N>` образы + `terraform apply` workspace `pr-<N>` + SSH-выкат + sticky-комментарий с URL; на `closed` → `terraform destroy` |
| Deploy | авто после `ECR Publish` на `main` (`workflow_run`) + `workflow_dispatch` | Не required | Не PR gate; реальный SSH-выкат на прод / откат |
| Infra — Provision prod host (Terraform) | `workflow_dispatch` (+ branch trigger для теста) | Не required | `terraform apply` для `terraform/prod/`; на первом запуске импортирует существующий EC2/SG в state |
| Infra — Bootstrap Terraform state | `workflow_dispatch` (+ branch trigger для теста) | Не required | Разовое создание S3-бакета `jsnotes-t2-tfstate` под Terraform state |

> Примечание: после перевода сборки на reusable `build-images.yml` имена
> nested-checks (ECR Publish/Preview) лучше свериться в GitHub UI перед тем, как
> делать их required.

Per-module lint/tests живут в CI самих сабмодулей (репозитории `api`/`ui`), а не в monorepo.

Важно: в monorepo workflow запускаются с `paths` filter:

- `Docker Compose CI` запускается только при изменениях в runtime/Docker Compose paths (включая bump указателей сабмодулей `api`/`ui`).
- `ECR Publish` на PR не запускается; на `main` или теге `v*.*.*` публикует image в Amazon ECR.

Если check сделать required в ruleset, но соответствующий workflow не запустился из-за `paths` filter, GitHub может оставить required check в `Pending` и заблокировать merge. Поэтому текущая безопасная политика для учебного проекта:

1. Оставить `paths` filters, чтобы не гонять лишние CI jobs на docs-only PR.
2. Не включать path-filtered checks как глобальные required checks для всех PR.
3. Использовать таблицу выше как список candidate checks для ручной проверки reviewer'ом.
4. Включать глобальные required checks только после появления always-running gate workflow или после решения гонять CI на каждый PR.

Docs-only PR без API/UI/Docker checks — ожидаемое поведение, а не баг.

Если GitHub не позволяет удобно сделать conditional required checks для разных путей, возможны три подхода:

1. Требовать только checks, которые реально появляются для PR.
2. Убрать `paths` filters и запускать оба CI workflow на каждый PR.
3. Добавить отдельный always-running CI Gate workflow, который сам решает, какие проверки релевантны для изменённых paths.

Для текущего этапа выбран безопасный вариант: оставить `paths` filters и зафиксировать ограничения в документации. CI Gate workflow можно добавить отдельной задачей, если команда захочет строгие required checks без лишних запусков.

## Current Ruleset Recommendation For `main`

Рекомендуемая настройка ruleset для текущего этапа проекта:

| Rule | Значение | Комментарий |
| --- | --- | --- |
| Ruleset name | `Protect main` | Основное правило для `main` |
| Enforcement status | `Active` | Включить после согласования с командой |
| Target branches | `main` | Защищаем default branch |
| Restrict deletions | Enabled | Запрет удаления `main` |
| Block force pushes | Enabled | Запрет переписывания истории `main` |
| Require pull request before merging | Enabled | Все изменения через PR |
| Required approvals | `1` | Минимальный review gate |
| Dismiss stale approvals | Recommended | Сбрасывать approval после новых commits |
| Require conversation resolution | Enabled | Не merge'ить с незакрытыми обсуждениями |
| Require status checks to pass | Use carefully | Не включать path-filtered checks глобально без CI Gate |
| Require deployments to succeed | Disabled now | Preview/dev deploy будет отдельной задачей следующего DevOps |

Минимальная безопасная конфигурация на сейчас: PR review + conversation resolution + запрет force push/deletion. Required checks включать только если команда понимает поведение `paths` filters.

## Pull Request Rules

Рекомендуемые правила для всех repositories:

| Setting | Рекомендация |
| --- | --- |
| Merge через PR | Required |
| Минимум approvals | `1` |
| Self-approval | Не использовать |
| Conversation resolution | Required |
| Delete branch after merge | Enabled |
| Auto-merge | Optional, лучше позже |

## Merge Strategy

Путь:

```text
Repository -> Settings -> General -> Pull Requests
```

Рекомендация для учебного проекта:

| Strategy | Рекомендация | Почему |
| --- | --- | --- |
| Squash merge | Enabled, default | Чистая история main, один commit на PR |
| Merge commit | Optional | Видны merge-коммиты, но история шумнее |
| Rebase merge | Optional | Требует аккуратности с историей |

Рекомендуемый default: `Squash merge`.

## GitHub Actions Permissions

Путь:

```text
Repository -> Settings -> Actions -> General
```

Рекомендуемые настройки:

| Setting | Рекомендация |
| --- | --- |
| Actions permissions | Allow all actions and reusable workflows или allow selected trusted actions |
| Workflow permissions | Read repository contents permission |
| Allow GitHub Actions to create and approve pull requests | Disabled, если нет отдельного workflow для этого |

Если workflow должен пушить коммиты, теги или packages, write permissions нужно обсуждать отдельно и выдавать точечно.

## Environments Protection

Сейчас в проекте только одно окружение — `production` (staging пока нет;
preview-per-PR — это «dev»-сторона, см. `preview-dev-environments-v2.md`):

```text
production
```

Путь:

```text
Repository -> Settings -> Environments
```

Рекомендации:

| Environment | Рекомендация | Зачем |
| --- | --- | --- |
| `production` | Включить required reviewers | Авто-деплой после merge будет ждать ручного approval |

`Deploy` workflow делает **реальный SSH-выкат** на постоянный прод-хост,
которым управляет Terraform (`terraform/prod/`, поднимается через `infra-prod.yml`;
S3-бакет под state создаётся разово через `infra-bootstrap.yml`). Сам деплой:
ECR login → `docker compose pull && up -d` → smoke `curl /api/v1/health`.
Запускается автоматически после `ECR Publish` на `main` (`workflow_run`) и
вручную (`workflow_dispatch`) для отката. Если SSH-секреты не заданы —
остаётся dry-run. Детали — [`deploy.md`](deploy.md) и [`preview.md`](preview.md).

## Secrets and Variables

Путь:

```text
Repository -> Settings -> Secrets and variables -> Actions
```

### Repository Secrets

| Secret | Где нужен | Назначение |
| --- | --- | --- |
| `GH_PAT` | monorepo CI | Checkout private submodules (**продублировать в Dependabot-секреты** — иначе гейт падает на PR от Dependabot) |
| `AWS_ACCESS_KEY_ID` | `ecr-publish`/`build-images`/`deploy` | Доступ в AWS/ECR (**используется сейчас**) |
| `AWS_SECRET_ACCESS_KEY` | то же | Секрет к ключу выше (**используется сейчас**) |
| `EMAIL_KEY` | preview/уведомления (позже) | Заведён курсом; в коде пока не используется |
| `SSH_HOST` / `SSH_USER` / `SSH_PRIVATE_KEY` | `deploy` | SSH на прод-хост (**используется** — реальный выкат) |
| `PROD_ENV_FILE` | `deploy` | Полное содержимое `.env.prod` (БД/OAuth/TTL); `deploy.yml` пишет его на хост (**используется**) |

`GH_PAT` должен иметь доступ к:

- `dmc-1-t2-notebook-mono`;
- `dmc-1-t2-notebook-api`;
- `dmc-1-t2-notebook-ui`.

Минимально нужные permissions:

- repository metadata read;
- repository contents read.

Если GitHub требует approve для organization token, token должен быть approved администратором организации.

### Repository Variables

| Variable | Где нужен | Пример |
| --- | --- | --- |
| `AWS_REGION` | `ecr-publish`/`build-images`/`deploy` | `eu-north-1` |
| `AWS_REPO_NAME` | generic от курса | `jsnotes` — в пайплайне **хардкодим** `jsnotes-t2` |
| `VITE_API_BASE_URL` | сборка UI-образа | `/api/v1` |

Variables подходят для несекретных значений. Secrets нужны для токенов, паролей и ключей.

## Dependabot

Путь:

```text
Repository -> Settings -> Code security and analysis -> Dependabot
```

Рекомендуется включить:

- Dependabot alerts;
- Dependabot security updates;
- Dependabot version updates.

Рекомендуемые ecosystems:

| Repository | Ecosystem |
| --- | --- |
| monorepo | `github-actions` |
| api | `pip` или `uv`, если позже перейдём на uv |
| ui | `pnpm` |

Для private submodules Dependabot также должен иметь доступ к нужным repositories.

## Issue Templates

Рекомендуется добавить `.github/ISSUE_TEMPLATE/`.

Минимальный набор:

| Template | Для чего |
| --- | --- |
| `bug_report.md` | Ошибки |
| `feature_request.md` | Новые функции |
| `devops_task.md` | CI/CD, Docker, GitHub settings, deployment |

Пример обязательных полей:

- Context;
- What should be done;
- Acceptance criteria;
- Related links;
- How to verify.

## Pull Request Template

Рекомендуемый файл:

```text
.github/pull_request_template.md
```

Минимальный шаблон:

```markdown
## Что изменено

-

## Зачем

-

## Проверка

- [ ] Локальные проверки выполнены
- [ ] GitHub Actions прошли
- [ ] Docker build проверен, если изменялся runtime

## Связанная задача

Closes #
```

## CODEOWNERS

Рекомендуемый файл:

```text
.github/CODEOWNERS
```

Пример:

```text
.github/workflows/ @team-or-user
docs/ @team-or-user
api/ @backend-team-or-user
ui/ @frontend-team-or-user
proxy/ @devops-team-or-user
docker-compose.yaml @devops-team-or-user
```

CODEOWNERS стоит включать после того, как команда договорится, кто отвечает за зоны проекта.

## Security

Рекомендуемые настройки:

| Setting | Рекомендация |
| --- | --- |
| Secret scanning | Enabled, если доступно |
| Push protection | Enabled, если доступно |
| Dependabot alerts | Enabled |
| Private vulnerability reporting | Optional |
| Branch force-push | Disabled для `main` |
| Branch deletion | Disabled для `main` |

## Recommended Setup Order

1. Настроить `GH_PAT` и убедиться, что CI умеет checkout private submodules.
2. Включить GitHub Actions.
3. Настроить Ruleset для `main`.
4. Включить required PR review.
5. Зафиксировать policy по required status checks с учётом `paths` filters.
6. Включить delete branch after merge.
7. Настроить Dependabot.
8. Добавить PR template.
9. Добавить issue templates.
10. Добавить CODEOWNERS после согласования зон ответственности.
11. Для `production` environment включить required reviewers перед реальным deploy.

## Проверка после настройки

Создать тестовый PR и проверить:

- прямой push в `main` запрещён;
- PR нельзя merge до завершения required checks;
- PR нельзя merge с failed checks;
- PR нельзя merge без required approval;
- после merge feature branch удаляется;
- GitHub Actions успешно подтягивает `api` и `ui` submodules.

## Handoff для следующего DevOps: Preview + Dev Environments v2

Текущий DevOps scope закрывает CI/CD foundation для проекта. Следующий DevOps scope будет расширять инфраструктуру до "живого" продукта:

- preview-развёртывания для каждой ветки / pull request;
- автоматический deploy после merge в основную ветку;
- оптимизация build caching;
- рабочие preview URL для каждого PR;
- обновлённый CI/CD pipeline для dev/production environments.

Что уже готово и может использоваться как база:

| Готово | Где |
| --- | --- |
| Per-module CI (lint/tests) | CI сабмодулей: `api/.github/workflows/`, `ui/.github/workflows/` |
| Docker Compose smoke test | `.github/workflows/docker-compose-ci.yml` |
| ECR publish для API/UI images | `.github/workflows/ecr-publish.yml` |
| Production compose из ECR images | `docker-compose.prod.yaml` |
| Deploy (auto + manual) — реальный SSH-выкат на прод | `.github/workflows/deploy.yml` |
| Terraform state-бакет (S3 + native locking) | `.github/workflows/infra-bootstrap.yml` + `terraform/bootstrap/` |
| Прод-хост через Terraform (с импортом существующего) | `.github/workflows/infra-prod.yml` + `terraform/prod/` |
| Preview-окружения per-PR (Terraform workspace + SSH-выкат) | `.github/workflows/preview.yml` + `terraform/preview/` |
| Deploy docs | `docs/deploy.md`, `docs/preview.md` |
| GitHub Environments | `production` |

Что не входит в текущий scope и должно быть отдельной задачей:

- TLS/домен (preview-URL пока `http://<ip>/`, без TLS);
- OIDC для AWS вместо статичных ключей в Secrets;
- automatic deploy on merge to `main`;
- AWS IAM/OIDC roles;
- real dev/prod secrets;
- domain/TLS;
- rollback workflow;
- monitoring/logging.

Важно: текущий ruleset не должен блокировать будущие preview workflows. После появления стабильных preview/dev deploy checks следующий DevOps должен пересмотреть required checks и решить, нужен ли always-running CI Gate workflow.

## Полезные ссылки

- Rulesets: https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-rulesets/about-rulesets
- Protected branches: https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-protected-branches/about-protected-branches
- Required status checks: https://docs.github.com/en/pull-requests/collaborating-with-pull-requests/collaborating-on-repositories-with-code-quality-features/troubleshooting-required-status-checks
- GitHub Actions permissions: https://docs.github.com/en/actions/security-guides/automatic-token-authentication
- Repository secrets: https://docs.github.com/en/actions/security-guides/using-secrets-in-github-actions
- Dependabot: https://docs.github.com/en/code-security/dependabot
- CODEOWNERS: https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/customizing-your-repository/about-code-owners
