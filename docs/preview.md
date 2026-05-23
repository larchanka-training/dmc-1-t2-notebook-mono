# Preview-окружения (per-PR) — CI/CD слой

> **Статус:** build-слой реализован; deploy/teardown — **scaffold** (каркас),
> ждёт инфраструктурного решения (Terraform). Архитектурный контекст и открытые
> вопросы — в [`preview-dev-environments-v2.md`](preview-dev-environments-v2.md).

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

## Что ещё НЕ подключено (TODO)

Помечено `# TODO(terraform):` прямо в `preview.yml`:

- реальный `terraform apply` preview-окружения и **рабочий Preview URL** в комментарии;
- `terraform destroy` при закрытии PR;
- вся Terraform-инфраструктура.

Зависит от открытых вопросов (remote state, EC2 vs shared host, домен,
автоудаление) — см. [`preview-dev-environments-v2.md`](preview-dev-environments-v2.md).

## Как достроить до реального деплоя

В `preview.yml`, на местах `# TODO(terraform)`:

```bash
# deploy:
terraform -chdir=terraform workspace select "pr-${PR_NUMBER}" \
  || terraform -chdir=terraform workspace new "pr-${PR_NUMBER}"
terraform -chdir=terraform apply -auto-approve -var "image_tag=${IMAGE_TAG}"
PREVIEW_URL=$(terraform -chdir=terraform output -raw preview_url)   # → в комментарий

# teardown:
terraform -chdir=terraform workspace select "pr-${PR_NUMBER}"
terraform -chdir=terraform destroy -auto-approve -var "image_tag=pr-${PR_NUMBER}"
terraform -chdir=terraform workspace delete "pr-${PR_NUMBER}"
```

После этого в sticky-комментарий вместо «⏳ ещё не подключён» подставляется
`${PREVIEW_URL}`.

## Секреты / переменные

- secrets (inherited): `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `GH_PAT`;
- встроенный `GITHUB_TOKEN` (для комментариев, нужен `pull-requests: write`);
- vars: `AWS_REGION`, `VITE_API_BASE_URL`;
- понадобится для Terraform: backend remote state (S3 + DynamoDB-lock).
