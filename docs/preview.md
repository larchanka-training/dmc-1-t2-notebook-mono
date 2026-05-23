# Preview-окружения (per-PR) — CI/CD слой

> **Статус:** build-слой реализован; deploy/teardown — **заблокированы правами**.
> Probe прав `deploy-user` показал: создавать EC2/SG и открывать порты можно, а
> **удалять — нет** (`ec2:TerminateInstances` / `DeleteSecurityGroup` запрещены),
> как и Terraform remote state (`s3:CreateBucket` / `dynamodb:CreateTable`).
> Поэтому preview ждёт расширения прав у админа (запрошены 2 права на удаление).
> Подход — **императивный** (без Terraform): окружение опознаётся по своей
> per-PR security group, а не по тегам. Контекст — в
> [`preview-dev-environments-v2.md`](preview-dev-environments-v2.md).

## Идея

Каждый pull request получает свои Docker-образы и (в будущем) своё временное
окружение с Preview URL. Окружение живёт, пока открыт PR, и удаляется при его
закрытии. Подробнее о модели (GitHub Flow, dev=preview, prod) — в decision-доке.

## Workflow-файлы

| Файл | Роль |
| --- | --- |
| `.github/workflows/build-images.yml` | **Reusable** (`workflow_call`): собирает api+ui → ECR. Единственный источник логики сборки |
| `.github/workflows/ecr-publish.yml` | Тонкий триггер на push `main` / тег → вызывает `build-images.yml` (prod-образы) |
| `.github/workflows/preview.yml` | На `pull_request` → вызывает `build-images.yml` (`pr-<N>`), деплой-каркас, teardown-каркас |
| `.github/workflows/docker-compose-ci.yml` | Интеграционный smoke-тест стека на PR (без изменений) |

Сборка вынесена в reusable, чтобы prod и preview **не дублировали** шаги и
отличались только триггером, тегом и concurrency.

## Теги (выбираются `metadata-action` по событию)

| Событие | Теги в ECR `jsnotes-t2` |
| --- | --- |
| push `main` | `api-/ui-latest` + `api-/ui-sha-<short>` |
| тег `v*.*.*` | `api-/ui-<semver>` |
| `pull_request` | `api-/ui-pr-<N>` (репо MUTABLE → перезаписывается на каждый push в PR) |

Preview собирается из тех же Docker-таргетов, что и prod (`api → runtime`,
`ui → production`), — чтобы preview зеркалил прод, а не dev-сборку.

## Что работает сейчас

На каждый PR (`opened`/`synchronize`/`reopened`):

1. `build` — собираются и пушатся `api-pr-<N>` / `ui-pr-<N>` в ECR.
2. `deploy` (scaffold) — валидируется `docker-compose.prod.yaml` с preview-тегом
   и в PR постится/обновляется sticky-комментарий со ссылками на образы.

На закрытии PR (`closed`):

3. `teardown` (scaffold) — комментарий о пометке окружения к удалению.

Concurrency: `preview-<N>`, `cancel-in-progress: true` — новый push отменяет
прошлую сборку.

## Что ещё НЕ подключено и почему

deploy/teardown в `preview.yml` — **каркас** (комментарии `# TODO` ещё в стиле
Terraform — это placeholder, реальный подход будет императивным). Блокер —
**права `deploy-user`**: нельзя удалять окружение (`ec2:TerminateInstances` /
`DeleteSecurityGroup` запрещены), значит preview нечем сносить при закрытии PR →
инстансы стали бы «вечными». Эти 2 права запрошены у админа.

Terraform для preview **отпал**: нужен remote state (S3 + DynamoDB), а
`s3:CreateBucket` / `dynamodb:CreateTable` тоже запрещены.

## Как достроим, когда дадут права (императивный подход)

Без Terraform и без тегов (`ec2:CreateTags` запрещён) — окружение PR опознаём по
его **per-PR security group** `jsnotes-preview-pr-<N>`:

```bash
# deploy (opened/synchronize): создать SG pr-<N> (порты 80) + run-instances в неё
#   (ECR-логин ключами deploy-user в user-data) ИЛИ, если инстанс уже есть,
#   зайти по SSH и docker compose pull && up -d. Public DNS → в sticky-комментарий.

# teardown (closed): найти инстанс по SG jsnotes-preview-pr-<N> →
#   terminate-instances → wait terminated → delete-security-group.
```

После этого в sticky-комментарий вместо «⏳ ещё не подключён» подставляется
реальный Preview URL. До выдачи прав `Terminate`/`DeleteSecurityGroup` шаг
teardown реализовать нельзя.

## Секреты / переменные

- secrets (inherited): `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `GH_PAT`;
- встроенный `GITHUB_TOKEN` (для комментариев, нужен `pull-requests: write`);
- vars: `AWS_REGION`, `VITE_API_BASE_URL`;
- для teardown понадобятся права `ec2:TerminateInstances` + `ec2:DeleteSecurityGroup`
  у `deploy-user` (запрошены у админа). Terraform/remote state НЕ нужны —
  подход императивный.
