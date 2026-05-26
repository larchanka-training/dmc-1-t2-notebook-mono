# Preview + Dev Environments v2 — решение и план

> **Статус:** decision record + **частично реализовано** (2026-05-23).
> Реализован build-слой и **каркас** preview (см. ниже «Статус реализации»).
> Реальный деплой/destroy окружений и Terraform-инфраструктура — ещё нет
> (зависит от открытых вопросов). Источник истины — код: по мере реализации этот
> и связанные документы (`deploy.md`, `ci-cd.md`, `AGENTS.md`, `preview.md`,
> `github-repository-settings.md`, `qa-plan.md`) приводятся в соответствие.

> **🔄 ОБНОВЛЕНИЕ (2026-05-24) — итоги probe прав `deploy-user`.**
> Реальная проверка прав изменила план (детали — в `deploy.md`):
> - **Terraform отпал** для прода и preview: `s3:CreateBucket` /
>   `dynamodb:CreateTable` запрещены → remote state негде хранить.
> - **Прод сделан и работает** — императивно (CLI, `infra-prod.yml` создаёт EC2)
>   + реальный SSH-выкат (`deploy.yml`). `deploy-user` может
>   `RunInstances`/`CreateSecurityGroup`/`AuthorizeSecurityGroupIngress`/`ecr:*`.
> - **Preview заблокирован**: запрещены `ec2:TerminateInstances` /
>   `DeleteSecurityGroup` (нечем сносить окружение PR) и `ec2:CreateTags`.
>   Запрошены 2 права на удаление у админа. Подход будет **императивным** (per-PR
>   security group вместо тегов/Terraform), не зависящим от S3.

> **🔄 ОБНОВЛЕНИЕ (2026-05-26) — все права выданы, Terraform внедрён.**
> Админ выдал недостающие права (`s3:CreateBucket`, `ec2:TerminateInstances`,
> `ec2:DeleteSecurityGroup`, `ec2:CreateTags`). Решения по итогу:
> - **Terraform возвращён** — и для прода, и для preview. Без DynamoDB:
>   S3-бэкенд использует **native locking** (`use_lockfile = true`,
>   Terraform ≥ 1.10). State-бакет создаётся разовым workflow
>   `Infra — Bootstrap Terraform state`.
> - **Прод** — `terraform/prod/`. Существующий EC2/SG **импортируется** при
>   первом запуске (`terraform import`), не пересоздаётся.
> - **Preview** — `terraform/preview/`, **workspace per PR** (`pr-<N>`). Каждый
>   PR получает свой EC2 + SG + Preview URL (`http://<ip>/`, без TLS).
>   Teardown через `terraform destroy` + `workspace delete` на `pull_request: closed`.
> - **Per-PR SG-имя** — `jsnotes-preview-pr-<N>-sg`, выводится из
>   `terraform.workspace` (а не из ручных тегов).
> - **Domain/TLS** — пока нет: URL preview = `http://<публичный IP>/`. Это
>   осознанное упрощение на время курса; домен/TLS — отдельная задача.
> - **`.env` для preview** — reuse'ится из секрета `PROD_ENV_FILE` (на курсе
>   стейджа нет, отдельный набор завести можно позже).
>
> Разделы ниже («Инструмент — Terraform», «workspaces», открытые вопросы) —
> исходное проектное решение, теперь оно соответствует реальности.

## Контекст / задача

Расширить инфраструктуру до «живого» продукта (`DEV + PROD`). Необходимо:

- preview-развёртывания для каждой ветки / pull request;
- автоматический deploy при merge в `main`;
- оптимизация build caching.

Результат: рабочие **preview-URL для каждого PR** + обновлённый CI/CD pipeline.

Связанный handoff: `docs/github-repository-settings.md` → раздел «Handoff для
следующего DevOps: Preview + Dev Environments v2».

## Ключевые решения

### 1. Модель ветвления — GitHub Flow

`feature → PR → main` напрямую. Отдельной долгоживущей ветки `dev` **нет**.
Роль «места проверки до прода» играет preview-окружение каждого PR, а не общая
ветка-прослойка.

### 2. Два типа окружений (а не три)

| Тип | Это же | Когда поднимается | Сколько живёт | Источник кода |
| --- | --- | --- | --- | --- |
| **dev / preview / PR** | «DEV» из задачи | PR открыт/обновлён | пока открыт PR | ветка PR |
| **prod** | «PROD» из задачи | merge в `main` | постоянно | `main` |

`dev` = `preview` = `pr` — это одно и то же окружение под разными именами.
Деплоим в два типа окружений, не в три.

### 3. Инструмент — Terraform (Infrastructure as Code)

Цикл `plan → apply` для прода и `plan → apply → destroy` для preview.
За основу берём примеры из
[futurice/terraform-examples](https://github.com/futurice/terraform-examples):

| Пример | Что берём |
| --- | --- |
| `aws_ec2_ebs_docker_host` | каркас EC2-хоста + EBS-том (под данные PostgreSQL) |
| `docker_compose_host` | паттерн доставки и запуска `docker-compose` на хосте |
| `aws_reverse_proxy` | опционально — красивые `pr-<N>.preview.<домен>` вместо голого IP |

### 4. Изоляция per-PR — Terraform workspaces

Каждый PR = workspace `pr-<N>` со своим state, чтобы окружения не затирали друг
друга. На `pull_request: opened/synchronize` → `apply` поднимает эфемерный
EC2 docker host этого PR (свой PostgreSQL-контейнер + EBS), запускает на нём
`docker compose` с образами `api-pr-<N>` / `ui-pr-<N>` из ECR. На
`pull_request: closed` → `destroy`.

Prod — отдельный долгоживущий workspace `prod`.

### 5. Переиспользуем существующее

- `ecr-publish.yml` — build + push в ECR (`jsnotes-t2`, теги `api-`/`ui-`).
  **Build caching уже сделан** (`type=gha, mode=max`, раздельные scope для
  api/ui) — требование №3 по сути закрыто.
- `docker-compose.prod.yaml` — стек из готовых ECR-образов.

## Целевая архитектура

```
GitHub PR ──► CI (GitHub Actions)
                 │ build api+ui ──► push в ECR (jsnotes-t2)        ← уже есть
                 │
                 ├─ PR открыт:   terraform workspace pr-<N> → plan → apply
                 │                 └─► EC2 docker host (свой) → docker compose up
                 │                       └─► Preview URL → коммент в PR (+ EMAIL_KEY?)
                 │
                 └─ PR закрыт:   terraform destroy → инстанс удалён

merge в main ──► build/push (есть) → terraform apply (prod) → compose pull/up
```

## Что меняется в pipeline

| Workflow | Действие |
| --- | --- |
| `ecr-publish.yml` | без изменений (сборка + кэш уже готовы) |
| `docker-compose-ci.yml` | остаётся как PR smoke-тест (это не preview) |
| `deploy.yml` | переделать: ручной dry-run → авто-деплой prod на `push: main` |
| `preview.yml` | **новый**: apply на PR / destroy на close + коммент с URL |
| `terraform/` | **новый**: backend (remote state) + модуль окружения |

## Секреты и переменные

Уже заведены (см. `docs/github-repository-settings.md` — раздел требует
обновления, см. найденные расхождения ниже):

- Secrets: `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `EMAIL_KEY`, `GH_PAT`.
- Variables: `AWS_REGION=eu-north-1`, `AWS_REPO_NAME=jsnotes` (generic; в
  пайплайне имя репозитория **хардкодим** как `jsnotes-t2`).

Понадобится дополнительно: backend для remote state (S3 + DynamoDB-lock) и,
возможно, secrets для домена/TLS.

## План реализации (порядок)

0. Закрыть открытые вопросы (ниже).
1. Каркас `terraform/`: backend (remote state) + модуль окружения (EC2 docker
   host + SG + EBS + Elastic IP).
2. **Вручную** `terraform apply` одного окружения → рабочее приложение по
   публичному адресу. Главный чекпоинт: путь Terraform → EC2 → ECR → URL живой.
3. `preview.yml`: обернуть шаг 2 в Actions (workspace per PR, apply/destroy,
   коммент с preview-URL).
4. `deploy.yml`: авто-деплой prod на merge в `main`.
5. Build caching — уже готов, отметить в отчёте.

## Статус реализации (обновляется по мере работ)

**Реализовано (2026-05-23):**

- `build-images.yml` — reusable workflow сборки api+ui → ECR; теги по событию
  (`latest`/`sha`/`semver`/`pr-<N>`).
- `ecr-publish.yml` — переведён на тонкий вызов `build-images.yml` (prod).
- `preview.yml` — на PR собирает `pr-<N>`-образы, валидирует prod-compose с этим
  тегом, постит sticky-комментарий в PR; на закрытии PR — шаг teardown.
- `deploy.yml` — переименован в `Deploy`; добавлен **авто-триггер**
  `workflow_run` после `ECR Publish` на `main` (+ сохранён ручной режим для
  отката). Это закрывает «автодеплой при merge» на уровне триггера.
- Build caching — было готово ранее, перенесено в reusable.

Детали слоя workflow — [`preview.md`](preview.md).

**Обновление (2026-05-24):**

- ✅ **Прод выкатывается реально** — `infra-prod.yml` (bootstrap EC2) + `deploy.yml`
  (SSH → ECR → `compose pull && up` → smoke). Императивно, без Terraform.
- ⛔ **Preview заблокирован** правами: нет `ec2:TerminateInstances` /
  `DeleteSecurityGroup` (нечем сносить). Запрошено у админа.
- ❌ **Terraform-инфраструктура** не делается — нет прав на S3/DynamoDB под state.

**Обновление (2026-05-26) — Terraform + preview включены:**

- ✅ **Terraform внедрён** — `terraform/{bootstrap,modules/docker_host,prod,preview}/`.
  Backend — S3 c `use_lockfile = true` (Terraform ≥ 1.10), без DynamoDB.
- ✅ **Прод** управляется Terraform (`terraform/prod/`); существующий EC2/SG
  импортируется (`terraform import` в `infra-prod.yml`), не пересоздаётся.
- ✅ **Preview-per-PR** работает: workspace `pr-<N>` → свой EC2 + SG → SSH-выкат
  compose → sticky-комментарий с `http://<ip>/`. На `closed` PR — `destroy`.
- ⏳ **Domain/TLS** — пока нет; preview-URL без TLS, по голому IP.

## Открытые вопросы (уточнить у курса)

1. **Remote state.** ⛔ ОТВЕЧЕНО probe'ом (2026-05-24): `deploy-user` НЕ может
   `s3:CreateBucket` / `dynamodb:CreateTable` → своими силами state-бэкенд не
   создать → **Terraform отложен**. Открыто к админу: дать готовый S3-бакет
   (+DynamoDB) ИЛИ права на их создание — тогда можно вернуться к Terraform.
2. **Per-PR хостинг.** Свой EC2 на PR (Terraform workspaces, чистый `destroy`)
   или общий хост + per-PR `docker compose -p`? Решение по умолчанию — свой EC2.
3. **Domain/DNS.** Есть зона под `*.preview.<домен>` или preview-URL = публичный
   IP / DNS-имя инстанса?
4. **`EMAIL_KEY`.** Для рассылки preview-ссылок / уведомлений о деплое? Какой
   провайдер (SES / SendGrid / Resend)?
5. **Размер инстанса и автоудаление.** Тип (`t3.micro/small`?), гасить preview
   при закрытии PR (и, возможно, по таймауту неактивности)?
6. **Модель окружений — РЕШЕНО (2026-05-23):** в проекте только `production`
   (+ preview-per-PR). Staging пока **нет**. `deploy.yml` упрощён до prod-only;
   авто-деплой целится в `production`. Staging можно добавить позже отдельной
   задачей (вернуть input `environment` + завести GitHub Environment).
   ⚠️ В `docs/qa-plan.md` (Local/CI/Staging/Production) и
   `docs/github-repository-settings.md` (Environments `staging`/`production`)
   ещё описан staging — поправить вместе с остальными pending-правками доков.

## Аудит документации: найденные расхождения (doc ≠ code)

> Проверено против реальных workflow 2026-05-23. **Правки в сами доки пока не
> внесены** — ждут согласования по каждому пункту. Здесь зафиксированы
> выверенные расхождения, чтобы их чинить осознанно и согласованно.

**Главное:** в репозитории сосуществуют **три несогласованные модели
окружений** — `staging`/`production` (`deploy.yml`, `deploy.md`, `AGENTS.md §6`,
`github-repository-settings.md`), Local/CI/Staging/Production (`qa-plan.md §5`,
стр. 179–186) и `dev`=preview-per-PR + `prod` (эта задача). Согласование — это
открытый вопрос №6 выше.

| # | Файл | Расхождение | Подтверждение в коде |
| --- | --- | --- | --- |
| 1 | `docs/ci-cd.md` (стр. 10) | «Frontend и Backend деплоятся **отдельно**»: собираются/публикуются как 2 образа — да, но **деплоятся вместе** одним стеком `docker-compose.prod.yaml`. (Часть про per-module CI и доки в сабмодулях — **корректна**.) | `docker-compose.prod.yaml`; ниже в самом `ci-cd.md` описан единый production-compose |
| 2 | `docs/github-actions-pr-checks.md` (стр. 44–59) | «Docker Build» стоит внутри **API CI / UI CI (= CI сабмодулей)**, где Docker-сборки нет. Реально образы собираются в monorepo: `docker compose build` на PR и `build-push-action` на main/тег. Опущены реальные джобы `CI complete` и UI `Unit tests` (coverage) | `api/.github/workflows/pull-request.yml` (lint/test/ci-complete), `ui/.github/workflows/pull-request.yml` (lint/test/build/ci-complete); `docker-compose-ci.yml:49`; `ecr-publish.yml:95` |
| 3 | `docs/github-actions-pr-checks.md` (стр. 26–30) | checkout сабмодулей показан как `with: token` + `submodules: recursive`, а workflow используют **ручной** способ `git config url.insteadOf` + `git submodule update` | `docker-compose-ci.yml:33-36`, `ecr-publish.yml:59-62` |
| 4 | `docs/github-repository-settings.md` (стр. 193–221) | Таблицы Secrets/Variables неполные: нет используемых **сейчас** `AWS_ACCESS_KEY_ID`/`AWS_SECRET_ACCESS_KEY` (secrets), `AWS_REGION`/`AWS_REPO_NAME` (vars), а также `SSH_*` и `EMAIL_KEY`. Перечислены неиспользуемые сейчас `DATABASE_URL`/`OAUTH_*`/`*_TTL` | `grep secrets./vars.` по `.github/workflows/` |
| 5 | `docs/deploy.md` (стр. 86–98) | `AWS_ACCESS_KEY_ID`/`AWS_SECRET_ACCESS_KEY` помечены как «будущие» секреты, но уже используются. «Будущие» — только `SSH_*` | `ecr-publish.yml:72-73` |

Дополнительно:

- `EMAIL_KEY` — secret заведён (скриншот курса), но в коде **не используется** —
  задел под уведомления v2.
- Имя ECR `jsnotes-t2` и схема тегов `api-`/`ui-` — **консистентны** во всех
  файлах. ✅

**Статус правок: ВНЕСЕНЫ (2026-05-23).** Все расхождения исправлены в доках:

- `ci-cd.md` — «деплоятся отдельно» → «собираются отдельно, деплоятся вместе»;
  generic `staging` → `production`;
- `github-actions-pr-checks.md` — убран фантомный `Docker Build`, добавлены
  реальные джобы (`Unit tests`/`CI complete`), исправлен метод checkout сабмодулей;
- `github-repository-settings.md` — Secrets/Variables дополнены (`AWS_*`,
  `EMAIL_KEY`, `SSH_*`, `AWS_REGION`/`AWS_REPO_NAME`), Environments → prod-only,
  `Manual Deploy` → `Deploy`, required-checks таблица обновлена;
- `deploy.md`, `AGENTS.md` — `Manual Deploy` → `Deploy`, auto+manual, prod-only;
- `qa-plan.md` — пометка, что staging пока не развёрнут (целевая модель).

Открытым остаётся только: точные имена nested-checks (ECR Publish/Preview) после
reusable-рефактора — свериться в GitHub UI перед тем, как делать их required.
