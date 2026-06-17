# JS Notebook — Disaster Recovery Runbook

> **Status:** draft, Sprint #3 (2026-06-16). Source of truth для:
> AWS Console / live `aws describe-*` (текущее состояние) и
> `terraform/` (intended state). Команды в этом документе используют
> канонические имена ресурсов из `terraform/`; переменные значения
> (например, текущая active task-definition revision) находятся через
> `describe-*` в момент инцидента, а не записываются в документ.
>
> Связанные документы: `docs/aws-cloud-migration.md`,
> `docs/preview-v2.md`, `docs/bedrock-smoke-test.md`, `docs/ci-cd.md`.

## Prerequisites

Перед использованием runbook убедитесь, что у вас есть:

1. **AWS credentials** на аккаунт `867633231218`, регион `eu-north-1`:
   - для диагностики (`describe-*`, `list-*`) — IAM user с
     `arn:aws:iam::aws:policy/ReadOnlyAccess`;
   - для recovery (rollback, restore, secret rotation) — права уровня
     `deploy-user` (ECS/RDS/S3/VPC/CloudFront/CloudWatchLogs/IAM/
     SecretsManager + `SecretsManagerReadWrite`);
   - на 2026-06-16 владелец аккаунта — преподаватель курса.
2. **AWS CLI v2** (`aws --version` ≥ 2.x).
3. **Session Manager plugin** для `aws ecs execute-command`
   (`brew install --cask session-manager-plugin` на macOS).
4. **GitHub CLI** (`gh`) с правом на запуск `workflow_dispatch` в
   `larchanka-training/dmc-1-t2-notebook-mono` (для rollback через
   `deploy-cloud.yml`).
5. Локально склонированный monorepo + submodules (`api/`, `ui/`).

Если чего-то нет — это не оправдание не открыть runbook, а первая
строка постмортема: «инцидент задержан на N минут из-за отсутствия
доступа у дежурного».

---

## 1. Scope, contacts, severity

### 1.1. Scope

Этот runbook покрывает production-инциденты JS Notebook (T2). В скоп
входит:

- prod ECS Fargate API сервис `jsnotes-t2-api`;
- prod RDS PostgreSQL `jsnotes-t2-db`;
- prod CloudFront дистрибутив (UI + API через `/api/v1/*`);
- prod S3 bucket `jsnotes-t2-frontend`;
- AWS Bedrock (Nova Lite/Micro) интеграция для Cloud-agent;
- Resend как provider для OTP email;
- AWS Secrets Manager containers `jsnotes-t2-*`;
- DNS / domain ownership (`jsnb.org`) на стороне Cloudflare.

Не в скопе:

- preview-per-PR slices (см. `docs/preview-v2.md`);
- локальная разработка (`docker-compose.yaml`);
- мульти-региональный disaster recovery (educational scope —
  только manual redeploy);
- инциденты на стороне разработчика (broken submodule pointer и т.п.).

#### Project status и контекст финансирования

JS Notebook — учебный проект, который post-Sprint #3 **продолжает
развиваться** (owner: Marat G.). Это значит, что runbook — реальный
operational документ, а не релизный артефакт, и follow-up'ы из §3.2,
§5.7, §6.8, §9.8, §10.11, §11.6 — настоящий roadmap, не «формальность».

**Структура владения ресурсами:**

| Ресурс                     | Владелец                | После курса                      |
|----------------------------|--------------------------|----------------------------------|
| AWS account `867633231218` **(shared с T1 team!)** | Преподаватель курса (account admin) | См. §11 Scenario G |
| Домен `jsnb.org` (Cloudflare) | Marat G.              | Остаётся (доступен под любым исходом) |
| Cloudflare Email Routing для `*@jsnb.org` | Marat G. | Бесплатно, остаётся; forward на личный gmail |
| Resend account              | Marat G. (личный)       | Остаётся                          |
| GitHub repos (mono/api/ui)  | `larchanka-training` org | Доступны read-only                |
| Bedrock model access        | Привязан к AWS account  | Уходит вместе с AWS account       |

> ⚠ **Shared course account.** AWS аккаунт `867633231218` используется
> и T2 (нами), и T1 (другая команда курса). Source: `docs/aws-cloud-migration.md`,
> `docs/ai-architecture.md` («shared course account»),
> `docs/preview-v2.md` (T1 ui/api repos). Это влияет на:
>
> - **Scenario D (secret leak):** утечка ключа `deploy-user` компрометирует
>   доступ к ресурсам **обеих** команд — обязательная notify-цепочка
>   T1 + AWS admin (§8.0 cascade);
> - **AWS Budget / quotas:** budget overrun T1 может тригернуть
>   suspend ресурсов T2 (и наоборот);
> - **IAM-изменения** через `deploy-user` влияют на обе команды;
> - **Region capacity / VPC limits:** уже были инциденты `VpcLimitExceeded`
>   из-за shared `5 VPCs per region` (см. `docs/aws-cloud-migration.md`).

**Три возможных исхода для AWS после окончания курса** (детально в
Scenario G, §11):

- **G.continue** — преподаватель продолжает оплачивать AWS;
- **G.handover** — оплата и ownership AWS переходят (потенциально к
  Marat G.); ограничение: AWS account creation/billing для резидентов
  РФ ограничены санкциями, потребуется проверка регистрации новой
  AWS Organization (alt: AWS reseller через 3rd country, AWS Free Tier
  account на ЕС / non-RF юр.лицо);
- **G.shutdown** — AWS закрывается; домен и Resend остаются у Marat'а;
  репозитории и локальный код целы; возможен будущий restart на
  свежей инфре.

Эта структура **критична для DevOps**: при Scenario D (secret leak) и
Scenario E (Bedrock budget) нужны точные владельцы каждого ресурса,
чтобы знать, у кого запрашивать ротацию.

### 1.2. Contacts

| Роль                          | Кто (на 2026-06-17)            | Когда вызывать                  |
|-------------------------------|--------------------------------|---------------------------------|
| AWS account admin (shared T1/T2) | Преподаватель курса         | Sev-1, ротация AWS-ключей, billing, IAM, quota requests, account-level kill |
| **T1 team contact**           | **TBD (нужен handle)**         | **Любое action, влияющее на shared resources: secret leak, IAM, billing spike, quota** |
| Domain owner (`jsnb.org`, Cloudflare) | Marat G.               | DNS-инциденты, ACM cert renewal, alias переключение |
| Resend account owner          | Marat G.                       | OTP email outage, ключ Resend, Verified Sender |
| Primary on-call (DevOps T2)   | Marat G.                       | Все инциденты Sev-1..3           |
| Backup on-call                | TBD (заполнить после Sprint #3) | Если primary недоступен          |
| Tech Lead T2                  | TBD до окончания курса         | Sev-1, архитектурные решения     |
| QA                             | TBD до окончания курса         | Post-recovery regression smoke   |

**Escalation chain для shared-account инцидентов:**

```
T2 on-call (Marat) → Преподаватель (AWS admin) → T1 team contact
                  ↑
            обязательно для Scenario D
            (любая утечка ключа) и Scenario E
            (Bedrock budget overrun)
```

**TBD-поля** — нормальное состояние для educational проекта на этом
этапе; заполняются в follow-up PR. **T1 contact — приоритет к
заполнению до публикации runbook'а** (без него §8 deploy-key cascade
не имеет полной recovery-цепочки).

### 1.3. Severity model

| Severity | Признаки                                                              | Реакция                                 |
|----------|-----------------------------------------------------------------------|-----------------------------------------|
| Sev-1    | Production недоступен; data loss; auth bypass; утечка ключей; XSS, исполнившийся у пользователя | Немедленная мобилизация; rollback / freeze; communication ко всем |
| Sev-2    | Major feature broken (sync, LLM cloud полностью); серьёзная деградация latency; rate-limit broken | Rollback в течение часа; работа в рабочее время с фокусом      |
| Sev-3    | Workaround есть; ограниченная UX-проблема; одна функция деградирует   | Plan в течение спринта                  |
| Sev-4    | Cosmetic, копирайт                                                    | Бэклог                                  |

Severity model согласована с QA release certification (`release-report.md`).

---

## 2. Environments and URLs

### 2.1. Production

| Параметр                        | Значение                                       |
|---------------------------------|------------------------------------------------|
| Primary URL                     | `https://jsnb.org`, `https://www.jsnb.org`     |
| CloudFront fallback URL         | `https://d3mdkzwy5yknm5.cloudfront.net`        |
| CloudFront distribution         | `E29EW3R1X0PB5W` (подтвердить `list-distributions`) |
| DNS                             | Cloudflare → ACM cert в `us-east-1` → CloudFront aliases |
| AWS region                      | `eu-north-1`                                   |
| AWS account                     | `867633231218`                                 |
| ECS cluster                     | `jsnotes-t2`                                   |
| ECS service                     | `jsnotes-t2-api`                               |
| Task family (API)               | `jsnotes-t2-api`                               |
| Task family (migrations)        | `jsnotes-t2-migrations`                        |
| ALB                             | `jsnotes-t2-alb` (HTTP only; TLS делает CloudFront) |
| RDS                             | `jsnotes-t2-db` (postgres 16, db.t3.micro)     |
| S3 (UI)                         | `jsnotes-t2-frontend`                          |
| Log group (API)                 | `/ecs/jsnotes-t2-api` (retention 14 дн.)       |
| Log group (migrations)          | `/ecs/jsnotes-t2-migrations`                   |
| Bedrock generator               | `eu.amazon.nova-lite-v1:0`                     |
| Bedrock guard                   | `eu.amazon.nova-micro-v1:0`                    |

### 2.2. Preview (shared layer, не покрыт этим runbook'ом)

| Параметр       | Значение                                  |
|----------------|-------------------------------------------|
| URL            | `https://d2e2ymc27fdfn5.cloudfront.net`   |
| Shared DB      | `preview_main`                            |
| Per-PR API     | `preview-pr-<N>` Fargate сервис            |
| UI             | под `/pr-<N>/` на shared CloudFront        |

Если preview сломался — это не Sev-1 для пользователей; чините по
обычному PR-флоу.

### 2.3. Smoke check (single source of truth)

После любой recovery-операции этот блок — финальная проверка:

```bash
# 1. CloudFront → S3 UI (200, контент с index.html)
curl -fsS -o /dev/null -w "UI: %{http_code} %{size_download}b %{time_total}s\n" \
  https://jsnb.org/

# 2. API health через CloudFront
curl -fsS https://jsnb.org/api/v1/health
# Ожидание: 200 OK + JSON { "status": "ok", ... }

# 3. OTP request (на тестовый email)
curl -fsS -X POST https://jsnb.org/api/v1/auth/otp/request \
  -H 'Content-Type: application/json' \
  -d '{"email":"qa+runbook@jsnb.org"}'
# Ожидание: 202 Accepted (или 429 если попали в rate-limit — не ошибка)

# 4. ALB напрямую (если CloudFront → 5xx, надо понять, ALB или CF)
ALB_DNS=$(aws elbv2 describe-load-balancers --names jsnotes-t2-alb \
  --query 'LoadBalancers[0].DNSName' --output text)
curl -fsS "http://${ALB_DNS}/api/v1/health"
```

Если все 4 проходят — recovery считается успешным.

---

## 3. Section 0 — Detection and Paging

### 3.1. Текущее состояние detection

**Честно: detection в проекте сейчас реактивная — «узнаём от
пользователя или коллеги».** В IaC нет CloudWatch alarms (кроме
встроенного ECS circuit breaker), нет SNS topics, нет AWS Budgets,
нет uptime monitor'а. Это **самый большой operational gap проекта** и
зафиксировано в `_private/notes/sprint3/infra-baseline.md` §8.

Это значит, что на каждом сценарии §5–§11 есть **time-to-detect
gap**, который runbook сам по себе не закрывает. Дежурный должен
помнить про daily mini-smoke (§3.3). Per-scenario time-to-detect (TTD)
оценки:

| Scenario | Канал detection | TTD (typical) |
|----------|------------------|---------------|
| A — DB loss | API 5xx → жалоба user'а / ручной describe-services | 5–60 минут |
| B — API down | GH Actions `deploy-cloud.yml` red (sync с deploy); жалоба user'а (async) | 0–30 минут |
| C — Region outage | AWS Health page / запрос пользователя | 5–30 минут |
| D — Secret leak | GitHub secret-scan alert / abuse-pattern / внешний reporter | минуты — недели (хуже всего) |
| E — Bedrock budget | **Сейчас никак** (Cost Explorer lag ≥ 24h) → §9.1 для workaround | до 24+ часов |
| F — Resend outage | OTP request fail / Resend status page | минуты — часы |
| G — Sunset | Плановое событие (известная дата) | N/A |

Известные каналы сигналов:

| Источник                                      | Что показывает                              | Latency обнаружения       |
|------------------------------------------------|---------------------------------------------|---------------------------|
| Жалоба пользователя                            | UI/API недоступны                            | минуты — десятки минут    |
| GitHub Actions `deploy-cloud.yml` red          | Failed deploy / circuit-breaker rollback     | сразу после push          |
| GitHub Actions `infra-cloud.yml` red           | Failed Terraform apply / secret bootstrap    | сразу после merge         |
| Ручной просмотр CloudWatch Logs                | Startup errors, secret-related ошибки        | only when looked at        |
| Ручной `aws ecs describe-services`             | Сервис не stable, частые rollback events     | only when looked at        |
| AWS Health Dashboard                           | Региональные проблемы AWS                    | minutes after AWS notice  |
| CloudWatch Console metrics graphs              | Burst 5xx, RDS CPU, ALB UnHealthyHostCount   | only when looked at        |

### 3.2. Follow-up: operational observability (out of scope этого runbook'а)

Что нужно добавить, но делается **отдельной задачей** (DevOps month 1
roadmap Tech Lead'а):

- CloudWatch alarms: ECS service `RunningTaskCount < desiredCount`;
  ALB `HTTPCode_Target_5XX_Count` burst; RDS `CPUUtilization` > 80%;
  RDS `DatabaseConnections` near max; CloudFront `5xxErrorRate`.
- SNS topic с email subscription у дежурного.
- AWS Budget на Bedrock + ECS Fargate (требует расширения прав
  `deploy-user` — сейчас он не имеет `budgets:*`).
- CloudWatch Logs Metric Filters на паттерны:
  - `"validation error" "configuration"` → secret bootstrap fail;
  - `"NoCredentialsError"` → IAM role не attached;
  - `"AccessDeniedException"` → IAM policy regression.
- CloudWatch Dashboard, управляемый Terraform.

### 3.3. Что делать прямо сейчас, пока observability нет

Дежурный обязан раз в сутки в **любой рабочий день** запускать
mini-smoke (5 минут):

```bash
# CloudFront alive
curl -fsS -o /dev/null -w "%{http_code}\n" https://jsnb.org/
curl -fsS -o /dev/null -w "%{http_code}\n" https://jsnb.org/api/v1/health

# ECS service stable
aws ecs describe-services --cluster jsnotes-t2 --services jsnotes-t2-api \
  --query 'services[0].{Desired:desiredCount,Running:runningCount,Pending:pendingCount,LastStatus:deployments[0].rolloutState}' \
  --output table

# RDS available
aws rds describe-db-instances --db-instance-identifier jsnotes-t2-db \
  --query 'DBInstances[0].{Status:DBInstanceStatus,FreeStorageGB:`null`}' \
  --output table

# Recent API errors (последние 30 минут)
aws logs start-query --log-group-name /ecs/jsnotes-t2-api \
  --start-time $(date -u -v -30M +%s) --end-time $(date -u +%s) \
  --query-string 'filter @message like /ERROR|Exception|Traceback/ | stats count() by bin(5m)'
# Сохранить queryId, потом get-query-results
```

Это компенсирует отсутствие alarms за счёт регулярного «человеческого
polling». Не замена observability, а временный workaround.

### 3.4. Communication channels

| Канал                          | Когда                                      |
|--------------------------------|--------------------------------------------|
| Team chat (T2)                 | Открытие инцидента, статус каждые 30 мин   |
| GitHub Issue в `mono` repo     | Sev-1 / Sev-2: создать issue с label `incident` |
| `_private/summaries_memory/`   | Postmortem-summary после resolved          |

---

## 4. General incident flow

Один скелет для всех сценариев A–F. Каждый сценарий конкретизирует
шаги «Stop» и «Recover», остальное единообразно.

```text
1. IDENTIFY  ─── понять, что именно сломалось (симптомы, версия,
                 какой компонент).
2. SCOPE     ─── prod или preview? UI или API? data loss или downtime?
                 затронуты все пользователи или часть?
3. STOP      ─── остановить кровотечение: rollback, kill switch, rotate
                 secret, freeze deploy pipeline.
4. RECOVER   ─── шаги конкретного сценария (см. §5–10).
5. VERIFY    ─── §2.3 smoke check + специфичные для сценария проверки.
6. COMMUNICATE ─ статус в team chat + GitHub Issue update.
7. POSTMORTEM ── шаблон в §12; сохранить в
                 `_private/summaries_memory/`.
```

### 4.1. Identify — общие команды диагностики

```bash
# Является ли это региональной проблемой AWS?
# https://health.aws.amazon.com/health/status

# CloudFront/UI слой
curl -fsS -o /dev/null -w "CloudFront UI: %{http_code} %{time_total}s\n" \
  https://jsnb.org/
curl -fsS -o /dev/null -w "CloudFront API: %{http_code} %{time_total}s\n" \
  https://jsnb.org/api/v1/health

# ALB слой (минуя CloudFront)
ALB_DNS=$(aws elbv2 describe-load-balancers --names jsnotes-t2-alb \
  --query 'LoadBalancers[0].DNSName' --output text)
curl -fsS -o /dev/null -w "ALB API: %{http_code} %{time_total}s\n" \
  "http://${ALB_DNS}/api/v1/health"

# ECS service состояние
aws ecs describe-services --cluster jsnotes-t2 --services jsnotes-t2-api \
  --query 'services[0].{TD:taskDefinition,Desired:desiredCount,Running:runningCount,Pending:pendingCount,Events:events[0:5].[createdAt,message]}' \
  --output json

# RDS состояние
aws rds describe-db-instances --db-instance-identifier jsnotes-t2-db \
  --query 'DBInstances[0].{Status:DBInstanceStatus,Engine:Engine,Endpoint:Endpoint.Address,Storage:AllocatedStorage,MultiAZ:MultiAZ}' \
  --output table

# Последние 50 строк логов API
aws logs tail /ecs/jsnotes-t2-api --since 30m --follow=false | head -100
```

### 4.2. Scope — таблица решений

| Что показывают команды §4.1                              | Скорее всего сценарий |
|----------------------------------------------------------|-----------------------|
| `CloudFront 5xx` + `ALB 5xx` + ECS service unhealthy     | B (API down)          |
| `CloudFront 5xx` + ALB OK                                | CloudFront/CF Function issue (редко) |
| ALB UnHealthyHostCount = desired, API tasks `STOPPED`    | B1 или B2              |
| RDS `Status != available`                                 | A                     |
| OTP user complaints + Resend dashboard red                | F                     |
| Сообщение о неожиданно большом счёте/количестве LLM запросов | E                  |
| Уведомление о скомпрометированном secret / public ключе   | D                     |
| Регион eu-north-1 в AWS Health Dashboard как degraded     | C                     |

### 4.3. Stop the bleeding — общие действия

Эти действия безопасны даже без полной диагностики и не делают хуже:

1. **Freeze deploy pipeline:** в GitHub отключить
   `deploy-cloud.yml` (Actions → workflow → Disable), чтобы новый
   merge в `main` не наслоил вторую проблему на первую.
2. **Сохранить evidence:** screenshot CloudFront/ECS/RDS console;
   копия `describe-services` + `events` в файл; tail логов в файл.
   Это нужно для postmortem.
3. **Не делать `terraform apply`** во время инцидента — он перепишет
   часть task definition и затруднит rollback.
4. **Сообщить:** статус-пост в team chat: «Sev-X, симптомы такие-то,
   занимаемся».

Конкретный «stop» для каждого сценария — в §5–10.

### 4.4. Recover, Verify, Communicate, Postmortem

- Recover: см. конкретный сценарий §5–10.
- Verify: §2.3 smoke + специфичные шаги сценария.
- Communicate: статус каждые 30 минут в team chat; финальное
  сообщение «Resolved at HH:MM».
- Postmortem: шаблон в §12; сохранить файл вида
  `_private/summaries_memory/incident_<YYYY-MM-DD>_<short>.md`.

---

## 5. Scenario A — Database loss / corruption

**Severity:** Sev-1 (data loss или production down) / Sev-2 (только
deploy red, API не пострадал). TTD: 5–60 минут (см. §3.1).

### 5.0. Архитектурные особенности, определяющие RTO/RPO

- **RDS single-AZ** (`multi_az = false` в `terraform/modules/data`).
  Failover мгновенный из Multi-AZ невозможен — любая авария instance
  требует **manual restore**, что определяет нижнюю границу RTO в 30+
  минут.
- **Нет read replica.** Невозможно promote stand-by — только PITR /
  restore-from-snapshot.
- **Нет cross-region snapshot copy.** При region outage backup'ы
  потенциально недоступны (см. §11.6 follow-up + §17 Appendix D).
- **Notebooks в offline-first IndexedDB** на клиенте: **локальные**
  notebook'и пользователей **не теряются** даже при полной потере БД —
  только серверные синхронизированные копии. Sync ручной, поэтому
  user-side RPO **обычно лучше** DB-side RPO. **Browser execution
  (QuickJS) и in-browser AI (WebLLM) продолжают работать при
  полностью лежащем backend.** Это **снижает user impact** в Scenario A
  до «нельзя залогиниться + нельзя sync-нуть» вместо полной недоступности.

### 5.1. Что считать database loss

5 классов проблем, которые попадают в этот сценарий:

| Класс | Симптом | Куда смотреть | Подсценарий |
|-------|---------|----------------|-------------|
| A1. Instance gone | `aws rds describe-db-instances` → `DBInstanceNotFound`; ECS `connection refused` | RDS Console, CloudTrail | A.recover.instance |
| A2. Instance unhealthy | RDS `Status != available` (failed, storage-full, incompatible-parameters) | RDS Console events | A.recover.instance |
| A3. Data corruption / accidental delete | `psql` показывает пропавшие/повреждённые строки; bug report от пользователя | API logs, RDS console | A.recover.pitr |
| A4. Migration broken | ECS migration task `exit != 0`; deploy-cloud.yml red на migration step | `/ecs/jsnotes-t2-migrations` log group | A.recover.migration |
| A5. Wrong `DATABASE_URL` | API container crash на startup: `could not connect`, `password authentication failed` | `/ecs/jsnotes-t2-api` startup logs | A.recover.secret |

**Важно:** A4 и A5 — это **не** Sev-1 «data loss». Это config/deploy
проблемы, для которых rollback или secret update обычно достаточны.
Сценарии A3 (PITR) и A1/A2 (restore) самые «дорогие» по RTO.

### 5.2. Identify

```bash
# 1. Состояние RDS instance
aws rds describe-db-instances --db-instance-identifier jsnotes-t2-db \
  --query 'DBInstances[0].{Status:DBInstanceStatus,Endpoint:Endpoint.Address,Engine:Engine,LatestRestorableTime:LatestRestorableTime,BackupRetention:BackupRetentionPeriod,MultiAZ:MultiAZ,Storage:AllocatedStorage,DeletionProtection:DeletionProtection}' \
  --output table

# 2. События за последний день
aws rds describe-events --source-identifier jsnotes-t2-db \
  --source-type db-instance --duration 1440 \
  --query 'Events[].[Date,Message]' --output table

# 3. Startup-ошибки API
aws logs tail /ecs/jsnotes-t2-api --since 30m --filter-pattern '?ERROR ?Exception ?Traceback ?"could not connect" ?"password authentication"' \
  | head -200

# 4. Последний результат миграции
aws logs tail /ecs/jsnotes-t2-migrations --since 24h | tail -200

# 5. ECS deploy events (для отличия A5 от B1)
aws ecs describe-services --cluster jsnotes-t2 --services jsnotes-t2-api \
  --query 'services[0].events[0:10].[createdAt,message]' --output table
```

### 5.3. Decision tree

```
RDS Status != available?
  └── да   → A1/A2 (instance recovery, §5.4.1)
  └── нет
      ├── ECS migration task красный?
      │   └── A4 (migration recovery, §5.4.3)
      ├── API logs: "could not connect" / "password authentication"?
      │   └── A5 (secret recovery, §5.4.5)
      └── Bug report о data loss / wrong data в notebooks?
          └── A3 (PITR, §5.4.2)
```

> ❗ **После любого restore** (A1/A2/A3) — **обязательно** §5.4.4
> (Terraform drift loop). Без него auto-apply `infra-cloud.yml` может
> уничтожить восстановленный instance.

### 5.4. Recover

#### 5.4.1. A1/A2 — Instance recovery

Если instance потерян (A1) или unhealthy и не восстанавливается сам
(A2):

```bash
# Шаг 1. Проверить, что есть последний snapshot или PITR window
aws rds describe-db-snapshots --db-instance-identifier jsnotes-t2-db \
  --snapshot-type automated --query 'DBSnapshots[*].{Id:DBSnapshotIdentifier,Created:SnapshotCreateTime,Status:Status,Storage:AllocatedStorage}' \
  --output table

# Шаг 2. Восстановить из последнего automated backup до момента ДО
# инцидента (рекомендуется -5 минут от incident time)
TARGET_TIME="2026-06-17T10:25:00Z"  # за 5 минут до incident_time
RESTORED_ID="jsnotes-t2-db-restore-$(date +%Y%m%d%H%M)"

aws rds restore-db-instance-to-point-in-time \
  --source-db-instance-identifier jsnotes-t2-db \
  --target-db-instance-identifier "$RESTORED_ID" \
  --restore-time "$TARGET_TIME" \
  --db-subnet-group-name jsnotes-t2-db-subnet-group \
  --vpc-security-group-ids "$(aws ec2 describe-security-groups \
      --filters Name=group-name,Values=jsnotes-t2-rds-sg \
      --query 'SecurityGroups[0].GroupId' --output text)" \
  --no-multi-az \
  --no-publicly-accessible \
  --deletion-protection \
  --db-instance-class db.t3.micro \
  --storage-type gp3

# Шаг 3. Ждать, пока restored instance перейдёт в available (10–30 мин)
aws rds wait db-instance-available --db-instance-identifier "$RESTORED_ID"

# Шаг 4. Узнать endpoint нового instance
RESTORED_ENDPOINT=$(aws rds describe-db-instances \
  --db-instance-identifier "$RESTORED_ID" \
  --query 'DBInstances[0].Endpoint.Address' --output text)
echo "Restored endpoint: $RESTORED_ENDPOINT"
```

Дальше **два варианта замены endpoint'а** в `DATABASE_URL`:

- **Вариант A (быстро, не Terraform-managed):** обновить secret вручную,
  потом приложить через Terraform reconcile отдельной задачей.
  RTO быстрее, но появляется drift.
- **Вариант B (через rename):** удалить старый instance + переименовать
  restored в `jsnotes-t2-db` (его endpoint станет тем же, что был).
  RTO дольше (≥ 10 мин на rename + DNS propagate), drift отсутствует.

**Решение в Sev-1:** идём вариантом A для быстрого восстановления;
после resolved открываем PR для reconcile.

Вариант A — обновление secret:

```bash
# Получить текущие creds из db-migration secret (там JSON с username/password)
CREDS=$(aws secretsmanager get-secret-value \
  --secret-id jsnotes-t2-db-migration --query SecretString --output text)
DB_USER=$(echo "$CREDS" | jq -r .username)
DB_PASS=$(echo "$CREDS" | jq -r .password)

# Сформировать новый DATABASE_URL (имя БД 'wiki' — см. infra-baseline.md §5)
NEW_URL="postgresql://${DB_USER}:${DB_PASS}@${RESTORED_ENDPOINT}/wiki"

# Записать новое значение в secret
aws secretsmanager put-secret-value \
  --secret-id jsnotes-t2-database-url \
  --secret-string "$NEW_URL"

# Также обновить db_migration JSON (для будущих миграций)
NEW_MIG=$(echo "$CREDS" | jq --arg u "jdbc:postgresql://${RESTORED_ENDPOINT}/wiki" '.url=$u')
aws secretsmanager put-secret-value \
  --secret-id jsnotes-t2-db-migration \
  --secret-string "$NEW_MIG"

# Применить через force-new-deployment ECS (новые tasks подтянут new secret)
aws ecs update-service --cluster jsnotes-t2 --service jsnotes-t2-api \
  --force-new-deployment

# Подождать стабилизации
aws ecs wait services-stable --cluster jsnotes-t2 --services jsnotes-t2-api
```

После recovery — Verify (§5.5).

#### 5.4.2. A3 — PITR для точечного восстановления данных

Когда instance жив, но **данные испорчены** (например, миграция
случайно удалила колонку с данными, или баг приложения затёр notebooks).

**Стратегия:** восстановить отдельный instance на момент ДО инцидента,
вытащить нужные таблицы/строки, импортировать в живой instance. Live
instance не трогаем.

```bash
# Шаг 1. Выбрать точное время до инцидента
TARGET_TIME="2026-06-17T10:25:00Z"  # за 5 минут до известного incident_time
RESTORED_ID="jsnotes-t2-db-pitr-$(date +%Y%m%d%H%M)"

# Шаг 2. Восстановить во временный instance
aws rds restore-db-instance-to-point-in-time \
  --source-db-instance-identifier jsnotes-t2-db \
  --target-db-instance-identifier "$RESTORED_ID" \
  --restore-time "$TARGET_TIME" \
  --db-subnet-group-name jsnotes-t2-db-subnet-group \
  --vpc-security-group-ids "$(aws ec2 describe-security-groups \
      --filters Name=group-name,Values=jsnotes-t2-rds-sg \
      --query 'SecurityGroups[0].GroupId' --output text)" \
  --no-multi-az --no-publicly-accessible \
  --db-instance-class db.t3.micro --storage-type gp3

aws rds wait db-instance-available --db-instance-identifier "$RESTORED_ID"

# Шаг 3. Получить endpoint
RESTORED_ENDPOINT=$(aws rds describe-db-instances \
  --db-instance-identifier "$RESTORED_ID" \
  --query 'DBInstances[0].Endpoint.Address' --output text)

# Шаг 4. Из bastion / ECS Exec контейнера сделать pg_dump только нужных таблиц
TASK_ARN=$(aws ecs list-tasks --cluster jsnotes-t2 --service-name jsnotes-t2-api \
  --desired-status RUNNING --query 'taskArns[0]' --output text)

aws ecs execute-command --cluster jsnotes-t2 --task "$TASK_ARN" \
  --container api --interactive --command "/bin/sh"

# Внутри контейнера:
# pg_dump "postgresql://${DB_USER}:${DB_PASS}@${RESTORED_ENDPOINT}/wiki" \
#   --table=users.notebooks --data-only > /tmp/notebooks.sql
# psql "$DATABASE_URL" < /tmp/notebooks.sql  # на ЖИВОЙ instance, аккуратно!

# Шаг 5. Удалить временный instance
aws rds delete-db-instance --db-instance-identifier "$RESTORED_ID" \
  --skip-final-snapshot
```

**Важно:** перед импортом в live instance согласуйте с Tech Lead — это
изменение пользовательских данных. Желательно сделать backup живых
данных до импорта (отдельный snapshot).

#### 5.4.3. A4 — Migration recovery

Когда `deploy-cloud.yml` упал на migration step.

> ⚠ **Семантика отказа Liquibase + PostgreSQL.** Postgres
> **автокоммитит DDL** — это значит, что даже если миграция «упала»
> и `deploy-cloud.yml` показал red, **часть DDL могла применится
> до момента отказа**. Liquibase changeset rollback работает только
> если вы явно описали `<rollback>` блоки в changeset'е (по умолчанию
> их нет!). Source of truth — таблица `databasechangelog`.

```bash
# Шаг 1. Прочитать почему упала миграция
aws logs tail /ecs/jsnotes-t2-migrations --since 60m | tail -300

# Шаг 2. Проверить состояние Liquibase taксиметрии (databasechangelog =
# source of truth; не file system, не Git)
# Через psql из ECS Exec:
# SELECT id, author, filename, dateexecuted, exectype, orderexecuted
#   FROM databasechangelog ORDER BY orderexecuted DESC LIMIT 10;
# SELECT * FROM databasechangeloglock;

# Шаг 2b. Сравнить с file system: для каждого изменения, отсутствующего
# в databasechangelog но присутствующего в changelog-master.xml —
# может быть partially applied DDL без записи в журнал (worst case).

# Шаг 3. Если databasechangeloglock застрял (LOCKED=true), снять lock:
# UPDATE databasechangeloglock SET LOCKED=FALSE, LOCKEDBY=NULL, LOCKGRANTED=NULL WHERE ID=1;

# Шаг 4. Если partial DDL применилась без записи в databasechangelog
# (нет `<rollback>` в changeset'е) — единственный чистый путь
# восстановления это PITR (§5.4.2 A3) на момент до запуска миграции.
# Forward fix новым changeset'ом возможен, но только если вы точно
# знаете, что именно из DDL применилось — а это часто непонятно из логов.
#
# Если же `<rollback>` блок есть в changeset'е и Liquibase их выполнил
# (видно в логах "Rolling back changeset ..."), DB консистентна —
# достаточно forward fix новым changeset'ом.
#
# НИКОГДА не редактировать применённый changeset — Liquibase
# проверяет hash.

# Шаг 5. Re-deploy через workflow_dispatch с правильным образом
gh workflow run deploy-cloud.yml \
  --ref main \
  -f api_image_tag=sha-<previous-good>
```

**Sev уровень:** обычно Sev-2 (deploy red, но old API revision live).
Sev-1 только если миграция повредила данные (тогда переходим в A3).

#### 5.4.4. ⚠ Обязательная подпроцедура: PITR → новый endpoint → Terraform drift loop

После любого restore (A1/A2/A3) **возникает дрейф между live и
Terraform state**. Без явной процедуры **следующий `terraform apply`
(или auto-apply на push в `main`!) может попытаться «починить»
реальность и пересоздать/откатить БД** — это второй инцидент поверх
первого.

**Обязательный порядок действий** при любом restore:

```bash
# Шаг 1. ЗАМОРОЗИТЬ infra-cloud.yml (auto-apply на push в main)
gh api -X PUT \
  /repos/larchanka-training/dmc-1-t2-notebook-mono/actions/workflows/infra-cloud.yml/disable

# Шаг 2. Выполнить restore из (§5.4.1, §5.4.2 или §5.4.5) —
#        получить $RESTORED_ID
#        и новый $RESTORED_ENDPOINT.

# Шаг 3. Обновить производные секреты на новый endpoint
aws secretsmanager put-secret-value --secret-id jsnotes-t2-database-url \
  --secret-string "postgresql://${DB_USER}:${DB_PASS}@${RESTORED_ENDPOINT}/wiki"

aws secretsmanager put-secret-value --secret-id jsnotes-t2-db-migration \
  --secret-string "$(jq -n --arg u "$DB_USER" --arg p "$DB_PASS" \
    --arg url "jdbc:postgresql://${RESTORED_ENDPOINT}/wiki" \
    '{username:$u,password:$p,url:$url}')"

# Шаг 4. Roll API на новые secrets
aws ecs update-service --cluster jsnotes-t2 --service jsnotes-t2-api \
  --force-new-deployment
aws ecs wait services-stable --cluster jsnotes-t2 --services jsnotes-t2-api

# Шаг 5. Smoke (§2.3 + §12.1). Сервис должен быть жив на старом
#        identifier'е секретов с новым endpoint'ом.
```

**Шаг 6 — выровнять Terraform state** (можно сделать в течение
суток после recovery, **но до unfreeze infra-cloud**):

```bash
# Опция A. Самый чистый путь — переименовать restored instance
#          обратно в jsnotes-t2-db, чтобы Terraform не видел drift.
#          Сначала выключить deletion_protection на восстановленном
#          инстансе:
aws rds modify-db-instance --db-instance-identifier "$RESTORED_ID" \
  --no-deletion-protection --apply-immediately

# Затем удалить старый "сломанный" инстанс (если он ещё существует).
# Затем rename restored в jsnotes-t2-db через modify-db-instance.
# Endpoint снова станет тем же, secrets не нужно обновлять.
# RTO: +20–30 минут.

# Опция B. Если переименовывать неудобно — выровнять Terraform state
# (более экспертно, требует terraform CLI и доступа к state):
cd terraform/cloud
terraform state rm 'module.data.aws_db_instance.this'
terraform import 'module.data.aws_db_instance.this' "$RESTORED_ID"
# Затем поправить identifier в variables / hardcode, чтобы plan был no-op.
```

**Шаг 7. ТОЛЬКО ПОСЛЕ Шага 6** — разморозить infra-cloud:

```bash
gh api -X PUT \
  /repos/larchanka-training/dmc-1-t2-notebook-mono/actions/workflows/infra-cloud.yml/enable

# Проверить, что следующий plan на main = no-op:
gh workflow run infra-cloud.yml --ref main
gh run watch
```

> ❗ **Самое опасное:** при включённом auto-apply кто-то мержит даже
> docs-only PR в `main` → `infra-cloud.yml` запускает `terraform apply`
> → Terraform видит «БД не та» → пытается уничтожить restored instance
> и создать новый с пустыми данными. **Поэтому freeze infra-cloud
> (Шаг 1) — не optional, а критичный.**

#### 5.4.5. A5 — Secret recovery (wrong `DATABASE_URL`)

Когда API не стартует из-за неправильного secret value:

```bash
# Шаг 1. Прочитать текущее значение (только если действительно нужно
# для диагностики; обычно достаточно sanity check без чтения)
aws secretsmanager describe-secret --secret-id jsnotes-t2-database-url \
  --query '{LastChanged:LastChangedDate,VersionsToStages:VersionIdsToStages}' \
  --output json

# Шаг 2. Если есть предыдущая версия (AWSPREVIOUS), быстрый rollback:
aws secretsmanager update-secret-version-stage \
  --secret-id jsnotes-t2-database-url \
  --version-stage AWSCURRENT \
  --move-to-version-id "$(aws secretsmanager describe-secret \
      --secret-id jsnotes-t2-database-url \
      --query 'VersionIdsToStages | to_entries | [?contains(value, `AWSPREVIOUS`)] | [0].key' \
      --output text)" \
  --remove-from-version-id "$(aws secretsmanager describe-secret \
      --secret-id jsnotes-t2-database-url \
      --query 'VersionIdsToStages | to_entries | [?contains(value, `AWSCURRENT`)] | [0].key' \
      --output text)"

# Шаг 3. Force-new-deployment, чтобы ECS подхватил восстановленный secret
aws ecs update-service --cluster jsnotes-t2 --service jsnotes-t2-api \
  --force-new-deployment

aws ecs wait services-stable --cluster jsnotes-t2 --services jsnotes-t2-api
```

### 5.5. Verify

1. Базовый smoke (§2.3) — все 4 проверки должны пройти.
2. DB-специфичные проверки:

```bash
# Проверить connection через API health (он делает SELECT 1)
curl -fsS https://jsnb.org/api/v1/health

# Проверить, что real DB-bound endpoint работает
# (OTP request делает INSERT в users.otps)
curl -fsS -X POST https://jsnb.org/api/v1/auth/otp/request \
  -H 'Content-Type: application/json' \
  -d '{"email":"qa+runbook@jsnb.org"}'

# Если есть test account с notebooks — проверить list:
# (требует валидный JWT, см. test fixtures)

# Через ECS Exec проверить databasechangelog (если был A4):
aws ecs execute-command --cluster jsnotes-t2 \
  --task "$(aws ecs list-tasks --cluster jsnotes-t2 \
      --service-name jsnotes-t2-api --query 'taskArns[0]' --output text)" \
  --container api --interactive \
  --command "python -c 'from app.db import engine; import sqlalchemy as sa; \
    print(engine.execute(sa.text(\"SELECT count(*) FROM databasechangelog\")).scalar())'"
```

### 5.6. RTO / RPO

| Подсценарий | RTO (целевое) | RPO (потенциальная потеря) |
|-------------|---------------|----------------------------|
| A1/A2 instance recovery | 30–60 мин (PITR + secret + roll) | ≤ 5 мин до `LatestRestorableTime` |
| A3 PITR data restore | 60–120 мин (PITR + dump/import + согласование) | определяется выбранным `--restore-time` |
| A4 migration recovery | 30–90 мин (фикс changeset + redeploy) | 0 (данные не теряются) |
| A5 secret recovery | 10–15 мин (revert version + roll) | 0 |

Эти цифры — **best effort для educational scope** (db.t3.micro,
single-AZ). В реальной production команде с Multi-AZ + read replicas
+ pre-rehearsed runbook'ом RTO для A1/A2 был бы 10–20 мин.

### 5.7. Что добавить follow-up'ом (не часть этого сценария)

- Restore drill на preview каждые 90 дней (`preview_main` DB не
  критична — можно потренироваться).
- Multi-AZ для RDS (фикс ≈ $15/мес доп., но снимает A1/A2 риск).
- Cross-region snapshot copy (для будущего Scenario C).
- Расширение прав `deploy-user` на `events:*` для CloudWatch event-rules
  на `RDS-EVENT-0009` (failover) и `RDS-EVENT-0006` (restart).

---

## 6. Scenario B — API down

**Severity:** Sev-1 (API недоступен) / Sev-2 (deploy red, но
сервис rolled-back на старую rev). TTD: 0–30 минут.

API недоступен или нестабилен: `https://jsnb.org/api/v1/health`
возвращает 5xx, `502`, `504`, или CloudFront показывает `503`. UI
обычно ещё открывается (он на S3+CloudFront), но любые auth/notebook
sync/LLM вызовы валятся.

Три подсценария:

- **B1.a — pipeline drift rollback:** `deploy-cloud.yml` исторически
  копировал env/secrets из live task-def (не из Terraform-базы),
  что приводило к тихому накоплению дрейфа неделями. Fix уже сделан
  (рендеринг из Terraform baseline через `deploy-cloud.yml:97`), но
  старая task-def с дрейфом может оставаться в истории revisions.
- **B1.b — config regression (startup fail-fast):** отсутствует/placeholder
  value в required secret под `APP_ENV=production` (см. PR #118 incident
  14.06). API не стартует, circuit breaker откатывает.
- **B2 — code crash:** новый образ падает на старте или в runtime.

Их Identify похож, Recover — радикально разный.

### 6.1. Identify (общая часть для B1/B2)

```bash
# 1. Проверить, что это именно API, а не CloudFront/ALB слой
ALB_DNS=$(aws elbv2 describe-load-balancers --names jsnotes-t2-alb \
  --query 'LoadBalancers[0].DNSName' --output text)

curl -fsS -o /dev/null -w "CloudFront: %{http_code}\n" https://jsnb.org/api/v1/health
curl -fsS -o /dev/null -w "ALB direct: %{http_code}\n" "http://${ALB_DNS}/api/v1/health"

# Если CloudFront 5xx и ALB 5xx → ALB или ECS, идём дальше.
# Если CloudFront 5xx и ALB 200 → CloudFront/CF Function (редкий случай, §6.5).

# 2. Состояние ECS service
aws ecs describe-services --cluster jsnotes-t2 --services jsnotes-t2-api \
  --query 'services[0].{TD:taskDefinition,Desired:desiredCount,Running:runningCount,Pending:pendingCount,RolloutState:deployments[0].rolloutState,RolloutStateReason:deployments[0].rolloutStateReason,Events:events[0:10].[createdAt,message]}' \
  --output json

# 3. Target group health (за UnHealthy hosts видно crash или slow start)
TG_ARN=$(aws elbv2 describe-target-groups --names jsnotes-t2-api-tg \
  --query 'TargetGroups[0].TargetGroupArn' --output text)
aws elbv2 describe-target-health --target-group-arn "$TG_ARN" \
  --query 'TargetHealthDescriptions[].{Target:Target.Id,Port:Target.Port,State:TargetHealth.State,Reason:TargetHealth.Reason,Desc:TargetHealth.Description}' \
  --output table

# 4. Последние logs API (откуда вылетел контейнер)
aws logs tail /ecs/jsnotes-t2-api --since 30m \
  --filter-pattern '?ERROR ?CRITICAL ?Exception ?Traceback ?"validation error" ?"startup"' \
  | head -300

# 5. Stopped tasks (если они есть — там reason остановки)
STOPPED=$(aws ecs list-tasks --cluster jsnotes-t2 --service-name jsnotes-t2-api \
  --desired-status STOPPED --query 'taskArns' --output json)
echo "$STOPPED" | jq -r '.[]' | while read TASK; do
  aws ecs describe-tasks --cluster jsnotes-t2 --tasks "$TASK" \
    --query 'tasks[].{StoppedReason:stoppedReason,StopCode:stopCode,Containers:containers[].{Name:name,ExitCode:exitCode,Reason:reason}}' \
    --output json
done
```

### 6.2. Decision tree: B1 vs B2

| Симптом из §6.1                                                   | Сценарий | Recovery   |
|--------------------------------------------------------------------|----------|-----------|
| `RolloutStateReason: ECS deployment <id> failed... circuit breaker` + log `"validation error" / "missing required"`+ имя secret в сообщении | **B1.b** (startup fail-fast) | §6.3.3 |
| `RolloutStateReason: ECS deployment <id> failed... circuit breaker` + log про **отсутствующий env var**, который должен был быть | **B1.a** (pipeline drift) | §6.3.4 |
| `RolloutStateReason: ECS deployment <id> failed... circuit breaker` + log `ImportError` / `Traceback` / `unhandled exception` | **B2**   | §6.4       |
| `stoppedReason: "Task failed ELB health checks"` + log без obvious crash | B2 (slow start или health path mismatch) | §6.4 |
| `stoppedReason: "Essential container in task exited"` + `exitCode: 1` + log `RuntimeError`/`Traceback` | **B2** | §6.4    |
| `stoppedReason: "ResourceInitializationError: ... unable to pull secrets ... AccessDenied"` | **B1.a** (IAM/secret ARN drift) | §6.3.4 |
| `Running == Desired`, но 5xx от ALB direct                         | B2 (runtime exception, не crash) | §6.4 |
| UI 200, ALB 5xx, ECS healthy                                       | CloudFront → ALB origin issue | §6.5 |

**Различение B1.a vs B1.b — по содержанию лога:**

- **B1.b (missing/placeholder secret value):** `pydantic.ValidationError`
  / «secret must be set», т.е. ARN привязан правильно, но **значение**
  в Secrets Manager отсутствует или placeholder. Fix — `put-secret-value`.
- **B1.a (env/secret drift в TD):** контейнер не получает ENV
  переменную, которая должна была быть (по Terraform baseline она
  есть, по реальной active TD — нет). Fix — пересоздать TD из
  Terraform baseline через `deploy-cloud.yml workflow_dispatch` или
  manual `register-task-definition` из IaC.

Реальный пример B1.b — `_private/summaries_memory/sprint2_follow-up/deploy_cloud_resend_secret_rollback_14_06_2026.md`:
после PR #118 production validation API стал требовать
`RESEND_API_KEY` и `EMAIL_FROM`, но Terraform/Secrets Manager их не
имели. ECS circuit breaker откатил deployment.

### 6.3. B1 — Config regression recovery

«Плохой» новый task definition + auto-rollback ECS оставил сервис
на **предыдущей живой** revision. Чаще всего сервис уже жив, чинить
надо: (a) не дать следующему деплою наступить на те же грабли,
(b) понять и устранить root cause.

#### 6.3.1. Stop the bleeding

```bash
# 1. Freeze prod deploy pipeline (GitHub UI):
#    Actions → "Deploy Cloud" workflow → ··· → Disable workflow
#    (или через API:)
gh api -X PUT \
  /repos/larchanka-training/dmc-1-t2-notebook-mono/actions/workflows/deploy-cloud.yml/disable

# 2. Подтвердить, что service rolled back и стабилен на старой revision
aws ecs describe-services --cluster jsnotes-t2 --services jsnotes-t2-api \
  --query 'services[0].{TD:taskDefinition,Desired:desiredCount,Running:runningCount,RolloutState:deployments[0].rolloutState}' \
  --output table
# Ожидание: rolloutState=COMPLETED, Running==Desired
```

#### 6.3.2. Diagnose root cause

```bash
# Сравнить failed revision vs предыдущую (что добавилось в env/secrets/image)
FAILED_TD_ARN=$(aws ecs describe-services --cluster jsnotes-t2 \
  --services jsnotes-t2-api \
  --query 'services[0].deployments[?status==`FAILED`] | [0].taskDefinition' \
  --output text)

# Если FAILED_TD_ARN пустой — события могли уже выкатиться из describe-services,
# смотрим историю TD revisions:
aws ecs list-task-definitions --family-prefix jsnotes-t2-api \
  --sort DESC --max-items 5 --output table

# Расшифровка failed revision
aws ecs describe-task-definition --task-definition "$FAILED_TD_ARN" \
  --query 'taskDefinition.containerDefinitions[0].{Image:image,Env:environment,Secrets:secrets[].name}' \
  --output json
```

5 типичных классов B1, которые runbook покрывает явно:

| Класс B1                                  | Как лечить                                  |
|--------------------------------------------|---------------------------------------------|
| Отсутствует Secrets Manager value (как PR #118) | §6.3.3 — поставить secret value, перезапустить |
| Secret ARN в TD устарел (был removed/replaced) | Откатить TD или починить Terraform, см. §6.3.4 |
| Неправильное значение env (например, `APP_ENV=dev` на prod) | Откатить TD revision, фикс в Terraform     |
| IAM execution role потеряла разрешение на secret | Поправить inline policy, redeploy           |
| ECR image tag не существует / неверный image_tag | Откатить через `workflow_dispatch` с предыдущим SHA |

#### 6.3.3. Поставить недостающий Secrets Manager value (как PR #118)

```bash
# Пример: RESEND_API_KEY отсутствует
aws secretsmanager describe-secret --secret-id jsnotes-t2-resend-api-key \
  --query '{LastChanged:LastChangedDate,VersionsToStages:VersionIdsToStages}' \
  --output json
# Если VersionsToStages пустой / только initial placeholder — значение не ставилось

# Запросить ключ у владельца Resend account (преподаватель), затем:
aws secretsmanager put-secret-value --secret-id jsnotes-t2-resend-api-key \
  --secret-string "re_xxxxxxxxxxxxxxxxxxxxxxxxx"

aws secretsmanager put-secret-value --secret-id jsnotes-t2-email-from \
  --secret-string "noreply@jsnb.org"
# (EMAIL_FROM должен быть verified sender в Resend)

# Перевыкатить тот же task definition (force-new-deployment) — он
# подтянет уже исправленный secret value через execution role
aws ecs update-service --cluster jsnotes-t2 --service jsnotes-t2-api \
  --force-new-deployment

aws ecs wait services-stable --cluster jsnotes-t2 --services jsnotes-t2-api
```

#### 6.3.4. Откатить task definition на предыдущую известно-хорошую revision

Если service всё ещё на плохой revision (редко — обычно circuit breaker
уже откатил) или если pinning к предыдущей revision нужен явно:

```bash
# Список последних 5 revisions
aws ecs list-task-definitions --family-prefix jsnotes-t2-api \
  --sort DESC --max-items 5

PREV_TD_ARN="arn:aws:ecs:eu-north-1:867633231218:task-definition/jsnotes-t2-api:<N>"

aws ecs update-service --cluster jsnotes-t2 --service jsnotes-t2-api \
  --task-definition "$PREV_TD_ARN" \
  --force-new-deployment

aws ecs wait services-stable --cluster jsnotes-t2 --services jsnotes-t2-api
```

#### 6.3.5. Unfreeze pipeline

После Verify (§6.6) — снова включить workflow:

```bash
gh api -X PUT \
  /repos/larchanka-training/dmc-1-t2-notebook-mono/actions/workflows/deploy-cloud.yml/enable
```

### 6.4. B2 — Code crash recovery

Новый образ выкатился, но падает (на startup или в runtime).
В отличие от B1 — это **проблема кода**, не конфигурации. Чинить через
rollback к предыдущему immutable `sha-<short>` через `deploy-cloud.yml
workflow_dispatch`.

#### 6.4.1. Найти предыдущий «хороший» SHA

```bash
# Активный (плохой) image
ACTIVE_TD=$(aws ecs describe-services --cluster jsnotes-t2 \
  --services jsnotes-t2-api --query 'services[0].taskDefinition' --output text)
BAD_IMAGE=$(aws ecs describe-task-definition --task-definition "$ACTIVE_TD" \
  --query 'taskDefinition.containerDefinitions[0].image' --output text)
echo "BAD image: $BAD_IMAGE"
# Пример: 867633231218.dkr.ecr.eu-north-1.amazonaws.com/jsnotes-t2:api-sha-ce8f4c9

# Предыдущие SHA из git log на main (rollback к "последнему известно зелёному")
git -C ~/.../dmc-1-t2-notebook-mono log --oneline main -n 10
# Альтернатива: ECR list, отсортировать по pushedAt desc
aws ecr describe-images --repository-name jsnotes-t2 \
  --filter tagStatus=TAGGED \
  --query 'sort_by(imageDetails, &imagePushedAt)[-10:].{Tags:imageTags,Pushed:imagePushedAt}' \
  --output table | grep 'api-sha-'
```

Выберите предыдущий immutable `api-sha-<short>`, который точно был
зелёным (например, последний tag перед плохим merge).

#### 6.4.2. Rollback через workflow_dispatch

```bash
GOOD_SHA="sha-de50503"  # пример; подставьте реальный короткий SHA из ECR

# Запустить deploy-cloud.yml с конкретным tag
gh workflow run deploy-cloud.yml \
  --ref main \
  -f image_tag="$GOOD_SHA"

# Наблюдать запуск
gh run watch
```

`deploy-cloud.yml` (как описано в `AGENTS.md` §6):

- регистрирует новую TD revision из Terraform baseline, swap image на
  `api-${GOOD_SHA}`;
- запускает миграции как one-off ECS task (для rollback по коду
  миграция обычно no-op — если только rollback не пересекает
  schema-changing changeset, см. §6.4.4);
- rolling update ECS;
- ждёт `services-stable`;
- падает red, если circuit breaker откатил.

#### 6.4.3. Если pipeline недоступен — manual rollback

```bash
# Скопировать env/secrets/IAM из baseline TD, только image swap
GOOD_IMAGE="867633231218.dkr.ecr.eu-north-1.amazonaws.com/jsnotes-t2:api-${GOOD_SHA}"

# Получить baseline TD из Terraform output (intended state, не active)
cd terraform/cloud
BASE_TD_ARN=$(terraform output -raw api_task_definition_arn)

# Сделать копию с подменой image (jq):
NEW_TD_INPUT=$(aws ecs describe-task-definition --task-definition "$BASE_TD_ARN" \
  --query 'taskDefinition' --output json | \
  jq --arg img "$GOOD_IMAGE" '
    .containerDefinitions[0].image = $img |
    del(.taskDefinitionArn, .revision, .status, .requiresAttributes, .compatibilities, .registeredAt, .registeredBy)
  ')

NEW_TD_ARN=$(echo "$NEW_TD_INPUT" | aws ecs register-task-definition \
  --cli-input-json file:///dev/stdin \
  --query 'taskDefinition.taskDefinitionArn' --output text)

aws ecs update-service --cluster jsnotes-t2 --service jsnotes-t2-api \
  --task-definition "$NEW_TD_ARN" --force-new-deployment

aws ecs wait services-stable --cluster jsnotes-t2 --services jsnotes-t2-api
```

#### 6.4.4. Если плохой SHA уже применил schema-changing миграцию

Liquibase forward-only: откат кода не откатит схему. Тогда:

1. Проверить `databasechangelog` (§5.4.3), какой changeset был
   применён плохим деплоем.
2. Если ему **не нужны** новые колонки/таблицы для старого кода —
   можно безопасно делать rollback приложения (старый код просто их
   не использует).
3. Если старый код **сломается** на новой схеме — нужен forward fix
   changeset, не rollback. Это уже не Sev-1 incident, это hotfix
   через PR.

### 6.5. CloudFront → ALB origin issue (редко)

CloudFront возвращает 5xx, но ALB direct отвечает 200. Возможные
причины:

- CloudFront cache отдаёт stale 5xx ответ → инвалидация;
- ordered_cache_behavior `/api/v1/*` сломан после change в Terraform;
- ALB origin DNS изменился (ALB пересоздан → новый DNS).

```bash
# Инвалидировать кеш API path'а
DIST_ID="E29EW3R1X0PB5W"  # подтвердить list-distributions
aws cloudfront create-invalidation --distribution-id "$DIST_ID" \
  --paths "/api/v1/*"

# Проверить, что ALB origin указывает на текущий ALB DNS
aws cloudfront get-distribution-config --id "$DIST_ID" \
  --query 'DistributionConfig.Origins.Items[?Id==`api-alb`].DomainName' \
  --output text

# Сравнить с реальным ALB DNS
aws elbv2 describe-load-balancers --names jsnotes-t2-alb \
  --query 'LoadBalancers[0].DNSName' --output text
```

Если DNS расходится → `terraform apply` для синхронизации (выйти
из режима freeze) или manual update CloudFront origin.

### 6.6. Verify

1. Базовый smoke (§2.3).
2. Дополнительно для B:

```bash
# ECS rolled out без новых rollback events
aws ecs describe-services --cluster jsnotes-t2 --services jsnotes-t2-api \
  --query 'services[0].deployments' --output json
# Ожидание: ровно один deployment, rolloutState=COMPLETED

# Health через ALB direct
ALB_DNS=$(aws elbv2 describe-load-balancers --names jsnotes-t2-alb \
  --query 'LoadBalancers[0].DNSName' --output text)
curl -fsS "http://${ALB_DNS}/api/v1/health"

# Свежие логи без startup/runtime errors
aws logs tail /ecs/jsnotes-t2-api --since 5m \
  --filter-pattern '?ERROR ?Exception ?Traceback' | head -50
# Ожидание: пусто
```

### 6.7. RTO / RPO

| Подсценарий | RTO (целевое) | RPO |
|-------------|---------------|-----|
| B1 missing secret value | 15–25 мин (put-secret-value + force-new-deployment) | 0 |
| B1 TD revision rollback | 10–15 мин (update-service + wait) | 0 |
| B2 rollback через workflow_dispatch | 15–25 мин (deploy-cloud.yml run + миграции + roll) | 0 (миграции forward-only, см. §6.4.4) |
| B2 manual rollback | 10–20 мин (register-task-definition + update-service) | 0 |
| CloudFront cache stale | 5–10 мин (invalidation propagation) | 0 |

RPO = 0 потому что B-инциденты не теряют данные (если только не
сочетаются с A4, в этом случае идём по обоим).

### 6.8. Что добавить follow-up'ом

- **Pre-deploy secret check** в `infra-cloud.yml`: если
  `aws secretsmanager get-secret-value` возвращает пустой/placeholder
  — фейлить infra apply раньше, чем deploy упрётся в это. Частично
  реализовано (см. summary 14.06), расширить на все 4 auth secrets.
- **CloudWatch alarm** на `ECS-ServiceDeploymentFailed` event (через
  EventBridge rule → SNS).
- **CloudWatch metric filter** на `/ecs/jsnotes-t2-api` для паттерна
  `"validation error"` / `"missing required environment variable"`
  → counter → alarm.
- **`gh workflow run` checklist** в Prerequisites — какой именно
  `GH_PAT` scope нужен для запуска deploy-cloud.yml dispatch.

---

## 7. Scenario C — AWS region outage

**Severity:** Sev-1 (полный outage) / Sev-2 (degraded). TTD: 5–30 минут
(AWS Health page или жалоба пользователя).

Регион `eu-north-1` стал недоступным или сильно деградирован.

### 7.1. Честная оговорка

**Multi-region disaster recovery — out of scope** для текущего
educational setup'а:

- инфра развёрнута только в `eu-north-1`;
- нет cross-region RDS replication / snapshot copy;
- нет cross-region ECR image replication;
- нет cross-region failover на ALB/CloudFront origin (CloudFront
  глобален, но origin один);
- ACM cert и Cloudflare DNS — глобальны/external, переедут «бесплатно».

Цель этого раздела — **минимизировать downtime и data loss**, а не
обеспечить near-zero RTO. Если важна high-availability — это
architecture-level задача (Tech Lead month 2 roadmap).

### 7.2. Identify

```bash
# 1. AWS Service Health (region-wide)
#    https://health.aws.amazon.com/health/status
#    Если eu-north-1 → degraded / outage → подтверждение C.

# 2. Из другого региона: можно ли вообще получить ответ от AWS API в eu-north-1?
AWS_REGION=eu-north-1 aws ecs describe-services \
  --cluster jsnotes-t2 --services jsnotes-t2-api 2>&1 | head -20
# Если timeout / 5xx от api.ecs.eu-north-1.amazonaws.com → region issue.

# 3. CloudFront статус (он global — должен жить, даже если origin лежит)
curl -fsS -o /dev/null -w "CloudFront edge: %{http_code} %{time_total}s\n" \
  https://jsnb.org/static/  # static path обходит ALB origin

# 4. Cloudflare DNS статус (если jsnb.org не резолвится — это Cloudflare,
#    не AWS)
dig +short jsnb.org
```

### 7.3. Scope decision

| Что лежит                                           | Действия |
|------------------------------------------------------|----------|
| Регион полностью down, нет ETA от AWS                | §7.4 — manual cross-region redeploy на новый регион (RTO дни) |
| Регион degraded, есть ETA < 4 часов                  | §7.5 — wait + user communication, без действий |
| Только один сервис (например, RDS) деградирован      | вернуться к §5 / §6 для конкретного компонента  |
| eu-north-1 OK, но CloudFront global edge issue       | §7.6 — user сообщение, ждать AWS                |

В 90% случаев это §7.5 (wait), а не §7.4 (manual rebuild).

### 7.4. Manual cross-region redeploy (если регион не вернётся)

Это **последний resort**, занимает дни и требует владельца AWS
(преподавателя). Шаги:

1. **Declare major incident**, communicate пользователям ожидание дней.
2. **Freeze**: отключить все workflows (`infra-cloud.yml`,
   `deploy-cloud.yml`, ECR publish).
3. **Выбрать target region** среди тех, где Bedrock EU Geo profile
   доступен: `eu-central-1`, `eu-west-1`, `eu-west-3`.
4. **Скопировать ECR images в target region:**
   ```bash
   aws ecr describe-images --repository-name jsnotes-t2 \
     --region eu-north-1 --filter tagStatus=TAGGED \
     --query 'sort_by(imageDetails, &imagePushedAt)[-5:].imageTags' \
     > tags.json
   # Pull last-good images локально, push в target region's ECR.
   # Или (предпочтительно) скопировать через AWS CLI (cross-region ECR
   # replication, требует ECR replication rule — её нет → manual).
   ```
5. **Восстановить RDS из cross-region snapshot copy** — но snapshot
   copy в target region не настроена. Без неё RDS придётся восстанавливать
   из последнего экспортированного дампа (если есть; см. §11.2
   off-boarding checklist). RPO = время с последнего дампа (потенциально
   дни).
6. **Re-apply Terraform в новом регионе:**
   ```bash
   cd terraform/cloud
   AWS_REGION=eu-central-1 terraform apply \
     -var "aws_region=eu-central-1"
   ```
   ACM cert придётся пересоздать в `us-east-1` (уже там), aliases
   `jsnb.org`/`www.jsnb.org` переключить в Cloudflare на новый
   CloudFront домен.
7. **Восстановить secrets** (значения держим в archive — см. §11.2).
8. **Re-run Liquibase миграции** на восстановленном RDS.
9. **Smoke** (§2.3).

**RTO:** ≥ 24 часа. **RPO:** до последнего экспортированного дампа.

### 7.5. Wait + communication (типичный случай)

Если AWS обещает recovery в течение часов — просто ждём, не делаем
hot moves:

1. User-facing сообщение на `jsnb.org` (static HTML на CloudFront —
   меняем default S3 object на maintenance page):
   ```bash
   aws s3 cp ./maintenance.html s3://jsnotes-t2-frontend/index.html \
     --cache-control 'max-age=60' --content-type 'text/html'
   aws cloudfront create-invalidation --distribution-id E29EW3R1X0PB5W \
     --paths '/' '/index.html'
   ```
2. Twitter / email команды → объявление с ETA от AWS.
3. Мониторим AWS Health каждые 30 минут.
4. После восстановления — `aws s3 sync` обратно нормальный UI build.

### 7.6. CloudFront global edge issue

Очень редко: CloudFront edge сам деградирует. Действия:

- проверить через несколько edge-локаций (`https://www.whatsmydns.net/`
  или `curl --resolve jsnb.org:443:<edge-ip>` из разных VPN);
- если только один edge red → AWS сам перенаправит трафик;
- если все edge red → ждать.

Нет user-facing fix: глобальный CDN мы не контролируем.

### 7.7. Follow-up (Scenario C hardening)

Чтобы Scenario C превратился из «дни» в «часы», нужно (не часть этого
runbook'а, отдельная задача):

- **Cross-region RDS snapshot copy** — automated daily/weekly copy в
  второй регион (`eu-west-1`). Cost ≈ $5/мес за storage.
- **ECR cross-region replication rule** — настраивается через
  Terraform, нулевая стоимость для маленьких образов.
- **Bedrock cross-region readiness** — Nova EU Geo profile уже
  включает 4 региона; нужно убедиться, что IAM task role позволяет
  invoke на каждый.
- **Pre-baked Terraform var sets** для каждого target region.
- **Bilingual maintenance page** в S3 (всегда готова к выкладыванию).

---

## 8. Scenario D — Secret leak

**Severity:** Sev-1 для всех классов (AWS deploy-key, JWT, DB pwd,
Resend, GH_PAT, Cloudflare token). TTD: минуты (GitHub secret-scan) —
**недели** (если внешний reporter). Самый широкий TTD-разброс из
всех сценариев.

Ключ / пароль / token утёк наружу: попал в публичный репозиторий,
показан в скриншоте, отправлен не туда в Slack, замечен в логах
третьей стороны, или сообщён через bug bounty.

Это **Sev-1**, независимо от того, был ли уже abuse: time-to-rotate
определяет blast radius.

### 8.0. ⚠ Cascade-сценарий: AWS deploy-user ключ (HIGHEST priority)

**Утечка `AWS_ACCESS_KEY_ID` для `deploy-user` — самая опасная**,
потому что:

1. `deploy-user` имеет `SecretsManagerReadWrite` → может прочитать
   **все** secrets аккаунта (см. `docs/aws-cloud-migration.md`,
   `_private/notes/sprint3/infra-baseline.md` §4):
   `JWT_SECRET`, `OTP_HASH_SECRET`, `RESEND_API_KEY`, `EMAIL_FROM`,
   `DATABASE_URL`, `db-migration`. → **Все они считаются скомпрометированными**.
2. `deploy-user` может **деплоить** через `deploy-cloud.yml` →
   атакующий может выкатить malicious image в prod.
3. **Account shared с T1** (§1.1) → utечка влияет на ресурсы T1
   тоже. → **Обязательное уведомление T1 + AWS admin (преподавателя)**.

Поэтому recovery — это **не одна ротация, а каскад**.

#### Cascade procedure

```bash
# Шаг 0. Notify T1 + AWS admin (преподаватель). Используйте
#        escalation chain §1.2. БЕЗ этого шага — каскад незавершён.

# Шаг 1. Stop the bleeding — deactivate ключ (не delete)
aws iam update-access-key --user-name deploy-user \
  --access-key-id AKIA<LEAKED> --status Inactive

# Шаг 2. Заморозить deploy + infra pipelines в monorepo
gh api -X PUT \
  /repos/larchanka-training/dmc-1-t2-notebook-mono/actions/workflows/deploy-cloud.yml/disable
gh api -X PUT \
  /repos/larchanka-training/dmc-1-t2-notebook-mono/actions/workflows/infra-cloud.yml/disable
gh api -X PUT \
  /repos/larchanka-training/dmc-1-t2-notebook-mono/actions/workflows/ecr-publish.yml/disable

# Шаг 3. Создать новый ключ и обновить GitHub Secrets
NEW_KEYS=$(aws iam create-access-key --user-name deploy-user)
# Обновить в UI GitHub Secrets (mono, api, ui) — НЕ через CLI.

# Шаг 4. CloudTrail audit за период от leak до deactivate
LEAK_TIME="2026-06-17T08:00:00Z"
DEACT_TIME="2026-06-17T10:30:00Z"
aws cloudtrail lookup-events \
  --lookup-attributes AttributeKey=Username,AttributeValue=deploy-user \
  --start-time "$LEAK_TIME" --end-time "$DEACT_TIME" \
  --query 'Events[].{Time:EventTime,Event:EventName,Source:SourceIPAddress}' \
  > /tmp/audit-leak.json

# Особое внимание к GetSecretValue / PutSecretValue / RegisterTaskDefinition.

# Шаг 5. Cascade ротация всех secrets, которые могли быть прочитаны:
#   §8.3.3 JWT_SECRET
#   §8.3.4 OTP_HASH_SECRET
#   §8.3.5 DB password (+ обновление DATABASE_URL и db-migration)
#   §8.3.2 RESEND_API_KEY (через Marat)
# Каждый запускается ПОСЛЕДОВАТЕЛЬНО с verify между.

# Шаг 6. После cascade — verify pipeline на новых ключах:
gh workflow run infra-cloud.yml --ref main  # plan no-op
gh workflow run deploy-cloud.yml --ref main -f image_tag=<current sha>

# Шаг 7. ТОЛЬКО ПОСЛЕ зелёного pipeline — delete старый ключ
aws iam delete-access-key --user-name deploy-user --access-key-id AKIA<LEAKED>

# Шаг 8. Размораживаем pipelines
gh api -X PUT \
  /repos/larchanka-training/dmc-1-t2-notebook-mono/actions/workflows/deploy-cloud.yml/enable
gh api -X PUT \
  /repos/larchanka-training/dmc-1-t2-notebook-mono/actions/workflows/infra-cloud.yml/enable
gh api -X PUT \
  /repos/larchanka-training/dmc-1-t2-notebook-mono/actions/workflows/ecr-publish.yml/enable

# Шаг 9. Postmortem + T1 + AWS admin update — обязательно для
#        shared-account incident.
```

**RTO для full cascade:** 2–4 часа (минут 5 на deactivate + час на
cascade ротации + час на verify + buffer).

**RPO:** 0 для данных, но **time-of-exposure ущерб может быть
больше 0** (атакующий мог уже что-то прочитать).

### 8.1. Identify

Сначала — что именно утекло и где:

| Класс утечки                              | Признаки                                       |
|--------------------------------------------|------------------------------------------------|
| AWS access key (`AKIA…`)                   | GitHub leak alert; CloudTrail unusual API calls; неожиданный bill |
| `JWT_SECRET`                                | API logs с unexpected token claims; user-reported account access |
| `OTP_HASH_SECRET`                           | Нестандартный pattern в OTP attempts            |
| `RESEND_API_KEY`                            | Email из Resend dashboard, который мы не делали; новый verified sender |
| DB password / `DATABASE_URL`                | Подключения к RDS с неизвестных IP в логах      |
| `GH_PAT`                                    | GitHub audit log → API calls от unknown app     |
| Cloudflare API token                        | DNS изменения, которых мы не делали             |

```bash
# 1. GitHub secret-scan уведомление
gh api /repos/larchanka-training/dmc-1-t2-notebook-mono/secret-scanning/alerts \
  --jq '.[] | {created:.created_at,secret_type,state,locations:.locations_url}'

# 2. AWS CloudTrail (последний час) — необычные API вызовы
aws cloudtrail lookup-events --max-results 50 \
  --lookup-attributes AttributeKey=EventName,AttributeValue=ConsoleLogin \
  --query 'Events[].{Time:EventTime,User:Username,Region:AwsRegion,Source:SourceIPAddress}' \
  --output table

# 3. RDS connections не из ECS SG
aws rds describe-events --source-identifier jsnotes-t2-db \
  --source-type db-instance --duration 60 --output table

# 4. История логинов в API (если utверждение — "доступ к чужим notebooks")
aws logs filter-log-events --log-group-name /ecs/jsnotes-t2-api \
  --start-time $(date -u -v -1H +%s)000 \
  --filter-pattern '"unauthorized" "auth_failed" "invalid_token"' \
  | jq -r '.events[].message' | head -50
```

### 8.2. Decide rotation order

```
1. Скомпрометированный secret → revoke / rotate first (stop the bleeding)
2. Связанные с ним (cascading) secrets → rotate next
3. Sessions/tokens, подписанные старым секретом → invalidate
4. Audit за период от leak до rotation → выявить abuse
```

Cascading примеры:

- AWS access key → пере-выпустить → ротировать **все** secrets, которые
  могли быть прочитаны под этим ключом за период exposure (см. CloudTrail).
- DB password → пере-выпустить → обновить `DATABASE_URL` и
  `db-migration` secrets → roll API tasks → подумать про **полный
  audit** notebooks tables.
- `JWT_SECRET` → новый → **invalidate ВСЕ user sessions** (это
  user-facing решение, см. §8.3.3).

### 8.3. Rotation procedures по классам

#### 8.3.1. AWS access key (`AKIA…`) утёк

Самый частый сценарий: ключ запушен в git.

```bash
# Шаг 1. В AWS IAM Console: найти пользователя по ключу
aws iam list-access-keys --user-name deploy-user

# Шаг 2. Deactivate скомпрометированный ключ (НЕ delete сразу — может
# ломать pipeline; deactivate обратимо, delete нет)
aws iam update-access-key --user-name deploy-user \
  --access-key-id AKIA<LEAKED> --status Inactive

# Шаг 3. Создать новый ключ
NEW_KEYS=$(aws iam create-access-key --user-name deploy-user)
echo "$NEW_KEYS" | jq -r '.AccessKey | "AccessKeyId: \(.AccessKeyId)\nSecretAccessKey: \(.SecretAccessKey)"'

# Шаг 4. Обновить GitHub Secrets — НЕ через CLI (значение попадёт в
# shell history). Через GitHub UI:
#   Settings → Secrets and variables → Actions →
#   AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY → Update
# Repos: mono, api, ui — все три (preview workflows используют их).

# Шаг 5. Проверить, что pipeline проходит с новыми ключами:
#   - запустить `infra-cloud.yml` workflow_dispatch (no-op plan);
#   - запустить `deploy-cloud.yml` workflow_dispatch с current sha;
#   - дождаться green.

# Шаг 6. Только после успешного зелёного pipeline — delete старый ключ
aws iam delete-access-key --user-name deploy-user --access-key-id AKIA<LEAKED>

# Шаг 7. CloudTrail audit за период от утечки до deactivation
LEAK_TIME="2026-06-17T08:00:00Z"
DEACT_TIME="2026-06-17T10:30:00Z"
aws cloudtrail lookup-events \
  --lookup-attributes AttributeKey=Username,AttributeValue=deploy-user \
  --start-time "$LEAK_TIME" --end-time "$DEACT_TIME" \
  --query 'Events[].{Time:EventTime,Event:EventName,Source:SourceIPAddress}' \
  --output json > /tmp/audit-leak.json

# Шаг 8. Просмотреть на необычные API calls (отличающиеся от обычного
# pipeline pattern). Если есть — escalate to AWS account owner.
```

#### 8.3.2. RESEND_API_KEY утёк

Эскалация: владелец Resend account = Marat G. (см. §1.2). Rotation
делает он же.

```bash
# Шаг 1. В Resend dashboard (https://resend.com/api-keys):
#   - Revoke скомпрометированный ключ;
#   - Сгенерировать новый с тем же scope (sending only);
#   - Скопировать одноразовое значение.

# Шаг 2. Обновить Secrets Manager (новое значение)
aws secretsmanager put-secret-value --secret-id jsnotes-t2-resend-api-key \
  --secret-string "$(read -s -p 'paste new key: ' k && echo "$k")"

# Шаг 3. Force-new-deployment ECS — новые tasks подтянут new key
aws ecs update-service --cluster jsnotes-t2 --service jsnotes-t2-api \
  --force-new-deployment
aws ecs wait services-stable --cluster jsnotes-t2 --services jsnotes-t2-api

# Шаг 4. В Resend dashboard проверить Sent → нет ли отправок, которых
# мы не делали в период exposure. Если есть — флагнуть в Resend
# support + пользователям с потенциально пострадавшими адресами.

# Шаг 5. Обновить GitHub Secrets → RESEND_API_KEY (для infra-cloud.yml
# bootstrap). Через UI, не CLI.
```

#### 8.3.3. `JWT_SECRET` утёк — INVALIDATES ALL SESSIONS

Это самый user-painful класс утечки: ротация **выкидывает всех
пользователей**.

```bash
# Шаг 1. Communication PERED ротацией: написать пользователям
#   ("в HH:MM мы вынужденно перезапустим auth, вам потребуется заново
#    войти, ваши notebooks не пострадают") — даже если их немного.

# Шаг 2. Сгенерировать новый ключ ≥ 32 байт
NEW=$(openssl rand -base64 48)
echo "$NEW" | wc -c   # должно быть ≥ 32

# Шаг 3. Поставить новое значение
aws secretsmanager put-secret-value --secret-id jsnotes-t2-jwt-secret \
  --secret-string "$NEW"

# Шаг 4. Force-new-deployment ECS
aws ecs update-service --cluster jsnotes-t2 --service jsnotes-t2-api \
  --force-new-deployment
aws ecs wait services-stable --cluster jsnotes-t2 --services jsnotes-t2-api

# Шаг 5. Все access tokens, подписанные старым секретом, теперь
# отвергаются. Refresh tokens тоже (они валидируются по тому же ключу).
# Пользователи увидят 401 → UI редиректит на login → OTP заново.

# Шаг 6. В logs за период от leak до rotation — поиск unauthorized
# access patterns (см. §8.1, query 4).

# Шаг 7. unset NEW (не оставлять в shell history)
unset NEW
history -c 2>/dev/null || true
```

#### 8.3.4. `OTP_HASH_SECRET` утёк

OTP hash secret — pepper, которым хешируются OTP коды в БД. Утечка
позволяет атакующему генерировать valid hash → bypass OTP validation.

```bash
# Шаг 1. Сгенерировать новый
NEW=$(openssl rand -base64 48)

# Шаг 2. Поставить новое значение
aws secretsmanager put-secret-value --secret-id jsnotes-t2-otp-hash-secret \
  --secret-string "$NEW"

# Шаг 3. ВНИМАНИЕ: все pending OTP в БД (`users.otps` с
# не-NULL `confirmed_at IS NULL`) станут невалидны — пользователи,
# которые запросили OTP до ротации, не смогут им войти. Они должны
# запросить заново. Это short-term breakage (5–15 минут).
# Опционально: TRUNCATE pending OTPs через psql, чтобы скрыть путаницу.

# Шаг 4. Force-new-deployment ECS
aws ecs update-service --cluster jsnotes-t2 --service jsnotes-t2-api \
  --force-new-deployment
unset NEW
```

#### 8.3.5. DB password утёк

> ⚠ **Brief failure window.** Между шагами 1 и 3 у работающих API-tasks
> старый пароль (он в их env, кешированном из старого secret), а RDS
> уже отвергает старый. Это **ожидаемый кратковременный downtime
> 2–5 минут**. Lambda-based secret rotation не настроена. Порядок
> ниже минимизирует window, но не убирает его полностью.

```bash
# Шаг 1. Изменить master password RDS (apply-immediately)
NEW_PASS=$(openssl rand -base64 24 | tr -d '/+=')  # URL-safe

aws rds modify-db-instance --db-instance-identifier jsnotes-t2-db \
  --master-user-password "$NEW_PASS" --apply-immediately

# Подождать (1–3 мин)
aws rds wait db-instance-available --db-instance-identifier jsnotes-t2-db

# Шаг 2. Получить endpoint и собрать новые secret strings
EP=$(aws rds describe-db-instances --db-instance-identifier jsnotes-t2-db \
  --query 'DBInstances[0].Endpoint.Address' --output text)

aws secretsmanager put-secret-value --secret-id jsnotes-t2-database-url \
  --secret-string "postgresql://jsnotes:${NEW_PASS}@${EP}/wiki"

aws secretsmanager put-secret-value --secret-id jsnotes-t2-db-migration \
  --secret-string "$(jq -n --arg u "jsnotes" --arg p "$NEW_PASS" \
    --arg url "jdbc:postgresql://${EP}/wiki" \
    '{username:$u,password:$p,url:$url}')"

# Шаг 3. Roll API
aws ecs update-service --cluster jsnotes-t2 --service jsnotes-t2-api \
  --force-new-deployment
aws ecs wait services-stable --cluster jsnotes-t2 --services jsnotes-t2-api

# Шаг 4. Audit RDS connections за период exposure (нужны RDS logs
# если включены performance insights). Без них — можно только смотреть
# CloudWatch RDS metrics на abnormal connection counts.

unset NEW_PASS
```

**Drift note:** Terraform контролирует `random_password.db.result`.
После manual ротации появляется drift `aws_db_instance.this.password`.
Reconcile отдельным PR (regenerate в Terraform или import нового
password в state).

#### 8.3.6. GH_PAT утёк

```bash
# Шаг 1. В GitHub UI:
#   Settings → Developer settings → Personal access tokens →
#   найти token → Revoke

# Шаг 2. Создать новый PAT (fine-grained preferable):
#   - Repos: mono / api / ui (read+write);
#   - Workflows: read;
#   - Expiration: 90 дней.

# Шаг 3. Обновить GitHub Secrets `GH_PAT` во всех 3 repos (mono/api/ui).

# Шаг 4. Audit:
gh api /user/audit-log --paginate \
  --jq '.[] | select(.created_at > "2026-06-17T08:00:00Z") | {created:.created_at,action,actor,repo}'
# (доступно только для Enterprise; для personal acc — Settings →
#  Security → Audit log)
```

#### 8.3.7. Cloudflare API token / DNS-credential утёк

Эскалация: владелец домена `jsnb.org` = Marat G. (§1.2).

```bash
# Шаг 1. Cloudflare dashboard → My Profile → API Tokens →
#   Revoke скомпрометированный → создать новый.

# Шаг 2. Проверить DNS audit log (Dashboard → Audit Logs) на изменения
# за период exposure.

# Шаг 3. Verify все DNS records jsnb.org нетронуты:
dig +short jsnb.org A
dig +short www.jsnb.org A
dig +short jsnb.org TXT  # SPF / DKIM не подмененены
```

Если кто-то изменил A-record или MX-record за время exposure — это
**эскалация в Sev-1**: атакующий мог собрать OTP, отправляемые на
наши verified senders, или перенаправить трафик jsnb.org на свой
сервер.

### 8.4. Verify

После любой ротации:

1. Базовый smoke (§2.3).
2. Проверка ECS task свежий (новые secrets подтянулись):
   ```bash
   aws ecs describe-services --cluster jsnotes-t2 --services jsnotes-t2-api \
     --query 'services[0].deployments[?status==`PRIMARY`].{TD:taskDefinition,Started:createdAt,Status:rolloutState}' \
     --output json
   ```
3. Проверка, что compromised value больше не работает (попытаться
   использовать старый JWT / OTP / API key и убедиться, что → 401).
4. CloudTrail / GitHub audit log — нет дальнейшего abuse.

### 8.5. Postmortem

Утечка ключей **обязательно** требует постмортема:

- **Сколько времени** ключ был exposed (leak → deactivation).
- **Что мог сделать** атакующий за это время.
- **Что сделали** — было ли abuse, какой scope.
- **Почему утёк** — root cause (git push без `.gitignore`,
  screenshot в публичном чате, etc.).
- **Что меняем** — pre-commit hooks для gitleaks, ротация по
  расписанию, principle of least privilege.

Шаблон — §12.

### 8.6. RTO / RPO

| Класс утечки               | RTO до stop-the-bleeding | RTO до полной recovery |
|----------------------------|--------------------------|------------------------|
| AWS access key             | 5 мин (deactivate)        | 30–60 мин (rotate + pipeline verify) |
| `JWT_SECRET`               | 10 мин                    | 15 мин + user re-login |
| `OTP_HASH_SECRET`          | 10 мин                    | 15 мин                  |
| `RESEND_API_KEY`           | 5 мин (revoke в Resend)   | 20 мин                  |
| DB password                | 5 мин (RDS modify)        | 15–25 мин                |
| GH_PAT                     | 1 мин (revoke в GH UI)    | 10 мин                  |
| Cloudflare token           | 1 мин                     | 10 мин + DNS audit       |

RPO = 0 для всех классов (ротация ничего не теряет, кроме сессий
для `JWT_SECRET`).

### 8.7. Что добавить follow-up'ом

- **`gitleaks` pre-commit hook** в lefthook config (mono/api/ui).
- **GitHub secret scanning** (включён по умолчанию для public, проверить
  для private organization).
- **Регулярная ротация JWT_SECRET / OTP_HASH_SECRET** каждые 90 дней
  (с user communication).
- **Audit log centralization** — экспорт CloudTrail в S3 для долгосрочного
  хранения (вне 90-дневного окна AWS).
- **Принцип «no `get-secret-value` в обычной работе»** — в runbook
  явно подчёркнуто: `describe-secret` (метаданные) достаточно, value
  читать нельзя без incident.

---

## 9. Scenario E — Bedrock budget / limit exceeded

**Severity:** Sev-2 при приближении к budget'у; Sev-1 при подтверждённой
abuse-атаке. **TTD: до 24+ часов (худший в проекте)** — proactive
alerting сейчас отсутствует, см. §9.0.

LLM траты по Bedrock резко выросли или приближаются к budget'у. Может
быть из-за легитимной нагрузки, abuse (если кто-то нашёл способ обойти
auth/rate limit), или баг в backend (например, retry-loop без exponential
backoff).

### 9.0. ⚠ Detection gap — текущая реальность

**Сейчас перерасход обнаруживается только вручную и с большим
запозданием:**

- AWS Budget alert **отсутствует** (нет в Terraform, см.
  `_private/notes/sprint3/infra-baseline.md` §8; deploy-user не
  имеет `budgets:ModifyBudget` permission).
- Cost Explorer обновляется с **lag 24–48 часов**.
- AWS Bedrock CloudWatch metrics `Invocations` доступны почти
  realtime, но без alarm никто их не смотрит.
- Realtime сигнал — только throttling (когда AWS уже начал отбивать
  запросы), что = «продакшн уже сломан».

#### Промежуточный detection в зоне deploy-user — рекомендация

API уже пишет `prompt_tokens` и `completion_tokens` в structured logs
на каждый LLM-запрос (`docs/ai-architecture.md`). Это позволяет
сделать **CloudWatch Logs metric filter + alarm**, который **не
требует** account-level прав на `budgets:*` (только
`logs:PutMetricFilter` и `cloudwatch:PutMetricAlarm` — оба в scope
`deploy-user`).

Skeleton Terraform (для отдельного follow-up PR):

```hcl
resource "aws_cloudwatch_log_metric_filter" "llm_total_tokens" {
  name           = "${var.project}-llm-total-tokens"
  log_group_name = "/ecs/jsnotes-t2-api"
  pattern        = "{ $.event = \"llm.requested\" }"
  metric_transformation {
    name      = "LlmTotalTokens"
    namespace = "JsnotesT2/LLM"
    value     = "$.total_tokens"
    unit      = "Count"
  }
}

resource "aws_cloudwatch_metric_alarm" "llm_token_burst" {
  alarm_name          = "${var.project}-llm-token-burst"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "LlmTotalTokens"
  namespace           = "JsnotesT2/LLM"
  period              = 3600                    # 1 час
  statistic           = "Sum"
  threshold           = 100000                  # калибровать после baseline
  alarm_actions       = [aws_sns_topic.alerts.arn]
}
```

Это закрывает **самый большой TTD-gap проекта**. Tracked как HIGH
PRIORITY в §9.8 follow-ups (выше, чем стандартный CloudWatch alarms
setup).

### 9.1. Identify

```bash
# 1. AWS Cost Explorer — Bedrock usage за последние 7 дней
#    UI: https://console.aws.amazon.com/cost-management/home → Cost Explorer
#    Group by: Service → отфильтровать "Amazon Bedrock"
#    Сравнить с baseline (Sprint #3: ≈ $0.50–$2/день на 5–10 пользователей)

# 2. CloudWatch metrics (если включены Bedrock invocation metrics)
aws cloudwatch get-metric-statistics \
  --namespace AWS/Bedrock \
  --metric-name Invocations \
  --start-time $(date -u -v -24H +%Y-%m-%dT%H:%M:%S) \
  --end-time $(date -u +%Y-%m-%dT%H:%M:%S) \
  --period 3600 --statistics Sum \
  --dimensions Name=ModelId,Value=eu.amazon.nova-lite-v1:0 \
  --output table

# То же для guard модели
aws cloudwatch get-metric-statistics \
  --namespace AWS/Bedrock \
  --metric-name Invocations \
  --start-time $(date -u -v -24H +%Y-%m-%dT%H:%M:%S) \
  --end-time $(date -u +%Y-%m-%dT%H:%M:%S) \
  --period 3600 --statistics Sum \
  --dimensions Name=ModelId,Value=eu.amazon.nova-micro-v1:0

# 3. Application logs: LLM requests за последний час
aws logs filter-log-events \
  --log-group-name /ecs/jsnotes-t2-api \
  --start-time $(date -u -v -1H +%s)000 \
  --filter-pattern '"llm.requested"' \
  | jq -r '.events[].message' | head -100

# 4. Per-user distribution (anomaly check — один user генерирует много?)
aws logs start-query --log-group-name /ecs/jsnotes-t2-api \
  --start-time $(date -u -v -24H +%s) --end-time $(date -u +%s) \
  --query-string 'filter event="llm.requested" | stats count() by user_id | sort count desc | limit 20'
# Сохранить queryId, потом get-query-results
```

### 9.2. Triage

| Что видно                                              | Скорее всего | Действия |
|--------------------------------------------------------|--------------|----------|
| Linear рост Invocations, distribution per-user ровная  | Legitimate growth | §9.3 — capacity planning, не отключать |
| Spike Invocations + один user_id доминирует            | Single-user abuse / bug | §9.4.1 — block user + investigate |
| Spike + распределение по многим user_id                | Mass abuse или auth bypass | §9.4.2 — kill switch + security audit |
| Linear рост, **guard** invocations превышают generator | Bug в backend (guard зацикленный) | §9.4.3 — code rollback (см. §6 B2) |
| Cost растёт без роста Invocations                      | Output tokens растут (длинные ответы) | §9.4.4 — снизить max_tokens |

### 9.3. Capacity planning (не emergency)

Если рост легитимный, действия в обычном порядке:

1. Записать новый baseline в `_private/notes/sprint3/cost-baseline.md`.
2. Передать Eng#2 (cost optimization) для пересчёта 100/1k/10k scenarios.
3. Если приближаемся к $5/день (educational threshold) — флагнуть
   преподавателю как owner AWS billing.

Не делать ничего реактивного — runbook не нужен.

### 9.4. Emergency actions

#### 9.4.1. Block single user

Если один user_id доминирует:

> ⚠ **Архитектурный gap (2026-06-17):** в текущей схеме `users.users`
> (см. `api/app/modules/auth/models/user.py`) **нет** колонок
> `disabled_at` / `is_active` / `banned_at`. API не проверяет статус
> user'а перед запросом. Поэтому **изолированно заблокировать одного
> пользователя нельзя без code change**.
>
> Tracked: `larchanka-training/dmc-1-t2-notebook-api#73` (HIGH PRIORITY follow-up).

Workaround'ы, доступные прямо сейчас:

| Опция | Эффект | Когда применять |
|-------|--------|-----------------|
| Hard delete user row | Удаляются user + все его notebooks (CASCADE) | Подтверждённый bot/abuse, не legitimate user |
| Rotate `JWT_SECRET` (§8.3.3) | Выкидывает **всех** пользователей | Mass abuse, когда нельзя выделить одного |
| Cloud-agent kill switch (§9.4.2) | Останавливает Bedrock traffic для всех | Если abuse именно по LLM-пути |
| Wait для PR с `disabled_at` миграцией | 30–60 мин | Если abuse не критичен по cost |

Команды для hard delete (опасно — необратимо удаляет данные):

```bash
TASK=$(aws ecs list-tasks --cluster $ECS_CLUSTER --service-name $ECS_SERVICE \
  --desired-status RUNNING --query 'taskArns[0]' --output text)
aws ecs execute-command --cluster $ECS_CLUSTER --task "$TASK" \
  --container api --interactive --command "/bin/sh"

# Внутри контейнера (psql может быть недоступен в production image,
# тогда через python+SQLAlchemy):
# psql "$DATABASE_URL" -c "DELETE FROM users.users WHERE id = '<USER_UUID>';"
```

В большинстве случаев правильнее **сначала** kill switch (§9.4.2),
потом плановый PR с user-blocking миграцией.

#### 9.4.2. Cloud-agent kill switch (mass abuse)

Когда не понятно, кто abuse'ит, но cost растёт катастрофически: **выключить
Cloud-agent целиком**. In-browser WebLLM продолжит работать для тех,
у кого браузер поддерживает.

Уровень 1 — **app-level kill switch** (требует code change!):

> ⚠ **Подтверждено 2026-06-17 live verification:** env-флага
> `LLM_CLOUD_AGENT_ENABLED` **НЕТ ни в `api/app/`, ни в active task
> definition** (revision 44 на момент проверки). Поэтому Level 1 ниже
> описывает **target/future state**, не текущую возможность.
>
> **Сегодня в реальном инциденте — используйте только Level 2** (IAM
> revoke) ниже. После имплементации флага в коде + Terraform — Level 1
> станет доступен.
>
> HIGH-priority follow-up: реализовать флаг (см. §9.8).

```bash
# Когда флаг будет реализован, поставить env переменную, которая
# отключает Cloud-agent. Сейчас (2026-06-17) — НЕ работает.
# Текущий API НЕ проверяет переменную LLM_CLOUD_AGENT_ENABLED.

# Через task definition env (intent: новый TD revision с LLM_CLOUD_AGENT_ENABLED=false):
# Самый быстрый путь — overrides через `update-service` нельзя для env
# (ECS update-service не поддерживает env override без новой TD).
# Поэтому используем `aws ecs register-task-definition` с патчем:

ACTIVE_TD=$(aws ecs describe-services --cluster jsnotes-t2 \
  --services jsnotes-t2-api --query 'services[0].taskDefinition' --output text)

NEW_TD_JSON=$(aws ecs describe-task-definition --task-definition "$ACTIVE_TD" \
  --query 'taskDefinition' --output json | \
  jq '.containerDefinitions[0].environment += [
        {"name":"LLM_CLOUD_AGENT_ENABLED","value":"false"}
      ] | del(.taskDefinitionArn, .revision, .status, .requiresAttributes,
              .compatibilities, .registeredAt, .registeredBy)')

KILL_TD_ARN=$(echo "$NEW_TD_JSON" | \
  aws ecs register-task-definition --cli-input-json file:///dev/stdin \
  --query 'taskDefinition.taskDefinitionArn' --output text)

aws ecs update-service --cluster jsnotes-t2 --service jsnotes-t2-api \
  --task-definition "$KILL_TD_ARN" --force-new-deployment

aws ecs wait services-stable --cluster jsnotes-t2 --services jsnotes-t2-api
```

После активации kill switch:

- `/api/v1/llm/generate` возвращает 503 `LLM_CLOUD_AGENT_DISABLED`;
- UI должна показывать сообщение и переключаться на in-browser path
  (если доступен);
- traffic в Bedrock падает до 0.

Уровень 2 — **жёстче (если flag не работает или нет в коде)**:

```bash
# Убрать Bedrock invoke permission из task IAM role inline policy.
# Без права invoke API сразу будет получать AccessDeniedException и
# отдавать 503.
aws iam delete-role-policy --role-name jsnotes-t2-ecs-task \
  --policy-name jsnotes-t2-bedrock-invoke

# Восстановить, когда incident закрыт: terraform apply (Terraform
# вернёт policy).
```

Это более жёсткий путь — он создаёт Terraform drift, но **гарантировано**
останавливает Bedrock traffic, даже если в коде нет kill switch.

#### 9.4.3. Backend bug rollback (guard loop)

Если guard модель invoке'ится в loop из-за бага:

- Идти в §6 Scenario B2: rollback к предыдущему `sha-<short>`.
- После rollback — проверить, что guard invocations пришли в норму
  (CloudWatch metric).

#### 9.4.4. Снизить max_tokens / disable summary mode

Если cost растёт из-за длинных ответов (output tokens):

```bash
# Env vars (требует new TD revision, как в §9.4.2):
# LLM_MAX_OUTPUT_TOKENS=200       # вместо 1000
# LLM_SUMMARY_STRATEGY=compact-oldest  # вместо llm-based summarization
```

Это soft mitigation — Cloud-agent работает, но дешевле.

### 9.5. Manual AWS Budget (deploy_user без прав на Budgets API)

Поскольку Terraform не управляет AWS Budgets, ставим вручную через
Console — это делает преподаватель (owner AWS account):

1. AWS Console → Billing → Budgets → Create budget;
2. Type: Cost budget; Period: Monthly; Amount: $X (например, $30/мес
   для educational scope);
3. Email alerts: 80% / 100% threshold → email преподавателя + Marat'а;
4. Filter: Service = Amazon Bedrock — отдельный budget на LLM;
5. Сохранить screenshot настройки в
   `_private/notes/sprint3/budgets-screenshot.md`.

Это **не часть автоматизированного runbook'а**, но runbook ссылается
на этот budget как detection mechanism (вместо отсутствующего alarm).

### 9.6. Verify

После любой emergency меры:

```bash
# 1. Bedrock invocations упали до нуля / нужного уровня
aws cloudwatch get-metric-statistics --namespace AWS/Bedrock \
  --metric-name Invocations --period 300 --statistics Sum \
  --start-time $(date -u -v -1H +%Y-%m-%dT%H:%M:%S) \
  --end-time $(date -u +%Y-%m-%dT%H:%M:%S) \
  --dimensions Name=ModelId,Value=eu.amazon.nova-lite-v1:0

# 2. UI graceful degradation: открыть jsnb.org, попробовать AI-generate,
#    убедиться, что UI показывает понятное сообщение, а не 5xx error
curl -X POST https://jsnb.org/api/v1/llm/generate \
  -H "Authorization: Bearer <test-jwt>" \
  -H "Content-Type: application/json" \
  -d '{"prompt":"test"}'
# При kill switch: 503 с body { "code": "LLM_CLOUD_AGENT_DISABLED" }

# 3. Cost Explorer показывает остановку траты (lag 24–48 часов до
#    видимости в Cost Explorer — это нормально).
```

### 9.7. RTO

| Действие                             | RTO   |
|---------------------------------------|-------|
| Block single user через DB update    | 5–10 мин |
| App-level kill switch (новый TD)      | 10–15 мин (register-task-definition + roll) |
| IAM policy revoke (hard kill)         | 5 мин  |
| Снижение max_tokens                   | 10–15 мин |
| Code rollback (guard loop fix)        | 15–25 мин (см. §6.7 B2) |

RPO = 0 (траты прекращаются мгновенно, history сохраняется в CloudTrail).

### 9.8. Follow-up

- **`LLM_CLOUD_AGENT_ENABLED` флаг (HIGH PRIORITY)** — подтверждено
  2026-06-17 через live verification: флага **нет** в `api/app/` и нет
  в active TD (revision 44). §9.4.2 Level 1 в этом runbook'е описывает
  target/future state. **В реальном инциденте сегодня — только Level 2
  (IAM revoke)**.
  Tracked: `larchanka-training/dmc-1-t2-notebook-api#74` (api + sibling
  Terraform PR в `mono`).
- **User blocking механизм (HIGH PRIORITY)** — миграция Liquibase
  добавляющая `disabled_at TIMESTAMP NULL` в `users.users` + middleware
  в API. Tracked: `larchanka-training/dmc-1-t2-notebook-api#73`.
  Без этого §9.4.1 работает только через destructive workaround'ы.
- **CloudWatch alarm на Bedrock daily cost** — через Budgets API
  (после расширения `deploy_user` прав).
- **Per-user token budget** в БД — атомарный счётчик tokens-per-day,
  reset в полночь UTC. Защищает от single-user abuse без kill switch.
  Зависит от user blocking механизма выше.
- **Exponential backoff** в guard-modeling retries — защита от bug
  «retry-loop».
- **Anomaly detection** — если daily Bedrock cost > 3× rolling avg
  за 7 дней → alarm. Через CloudWatch Anomaly Detection.

---

## 10. Scenario F — Resend OTP outage

**Severity:** Sev-1 для F.outage / F.account_issue (новые users
заблокированы) / Sev-2 для F.backend (rollback может починить) /
Sev-3 для F.user_specific. TTD: минуты — часы (зависит от того,
жалуется ли user сразу).

OTP email не доходят пользователям → они **не могут войти** (auth
зависит только от OTP, паролей нет). Залогиненные пользователи с
валидным JWT продолжают работать (включая **offline-first WebLLM
и QuickJS** — см. §5.0).

### 10.1. Контекст: single point of failure

OTP email доставка идёт **только через Resend** (личный аккаунт Marat'а,
см. §1.2). Нет SES fallback. Это **известный архитектурный gap**,
зафиксирован как Track 3 follow-up.

Это значит:

- Любой outage Resend → 100% downtime auth-flow;
- Любая проблема с аккаунтом Marat'а в Resend (suspension, billing
  issue, account compromise) → тот же эффект;
- Verified sender (`noreply@jsnb.org`) привязан к Resend → если они
  снимут verification, не сможем отправить ни одного письма.

### 10.2. Identify

```bash
# 1. Resend status page
# https://status.resend.com/

# 2. API logs: ошибки send
aws logs filter-log-events --log-group-name /ecs/jsnotes-t2-api \
  --start-time $(date -u -v -30M +%s)000 \
  --filter-pattern '"resend" ?ERROR ?Exception ?"send_failed"' \
  | jq -r '.events[].message' | head -50

# 3. User reports: "не приходит OTP"
# Спросить у user'а: какой email? проверить spam folder? время запроса?

# 4. Самостоятельная отправка через Resend API
curl -X POST 'https://api.resend.com/emails' \
  -H "Authorization: Bearer $(aws secretsmanager get-secret-value \
       --secret-id jsnotes-t2-resend-api-key --query SecretString --output text)" \
  -H 'Content-Type: application/json' \
  -d '{
    "from": "noreply@jsnb.org",
    "to": "marat+runbook@gmail.com",
    "subject": "runbook test",
    "text": "if you see this, Resend works"
  }'
# Если 200 — Resend ok, проблема в нашем backend.
# Если 4xx/5xx — Resend issue или API key issue.
# unset history после теста (содержит API key через --query).
```

### 10.3. Decision tree

| Что показывает Identify                          | Скорее всего | Действия |
|--------------------------------------------------|--------------|----------|
| Resend status page = down/degraded                | F.outage     | §10.4 — wait + communication |
| Resend OK, наш backend `resend.send` exception    | Backend bug  | §10.5 — code rollback or fix |
| Resend OK, наш `from` отвергается (verification)  | Sender unverified | §10.6 — re-verify sender |
| Resend OK, тестовый curl работает, но user reports — нет | User-specific (spam/blocked) | §10.7 — пользовательская поддержка |
| Resend API key invalid                             | Key rotation issue или leak (см. §8.3.2) | §8 Scenario D |
| Account suspended Resend                           | F.account_issue | §10.8 — эскалация к Marat / Resend support |

### 10.4. F.outage — Resend service down

Не делаем hot moves, **ждём** и **коммуницируем**:

1. Сообщение на UI login page (через S3 + CloudFront, как в §7.5):
   ```bash
   aws s3 cp ./maintenance-otp.html s3://jsnotes-t2-frontend/maintenance-otp.html \
     --content-type 'text/html' --cache-control 'max-age=60'
   ```
   UI должна показывать «временно не приходят коды, попробуйте позже»
   при попытке OTP request. Это **UI change** — runbook не может
   деплоить новый UI на лету; реалистично — `maintenance-otp.html`
   как static page + редирект через CloudFront error pages.
2. Twitter / email-список: текущим зарегистрированным пользователям —
   «временно нельзя залогиниться, мы знаем». У уже залогиненных
   (валидный JWT) — продукт работает.
3. Мониторинг Resend status каждые 15 мин.
4. **Эскалация к Track 3 follow-up:** если outage > 4 часов —
   аргумент в пользу немедленной имплементации SES fallback.

### 10.5. F.backend — наш бекенд сломался

Treat as Scenario B (API down):

- Идти к §6 для diagnose.
- Если новый код добавил баг в send-path — rollback к предыдущему
  `sha-<short>` (§6.4).
- Если environment regression (например, `EMAIL_FROM` стал
  placeholder'ом) — Scenario B1 (§6.3.3).

### 10.6. F.sender_unverified — sender verification отозвана

Если Resend перестал принимать `noreply@jsnb.org`:

```text
1. Resend Dashboard → Domains → jsnb.org status check.
2. Если SPF/DKIM/MX records jsnb.org изменились или истекли:
   - проверить Cloudflare DNS audit log (за период с last successful
     send) — кто менял?
   - если auth: F.account_issue + Scenario D (utечка Cloudflare token).
3. Re-add SPF/DKIM записи в Cloudflare:
   - значения берутся из Resend Dashboard → Domains → Configure.
4. Дождаться DNS propagation (5–60 мин).
5. В Resend Dashboard → Verify Domain.
6. Тест send (§10.2 step 4).
```

### 10.7. F.user_specific — один пользователь не получает

Не Sev-1, обычно Sev-3:

- Проверить, что email есть в users table (`api/app/modules/users`).
- Проверить, не в Resend bounce/complaint list (Dashboard → Suppressions).
- Проверить, не блочит ли его email-provider (corp Gmail с anti-phishing,
  Mail.ru с anti-spam).
- Если bounce list — попросить user'а проверить spam, попросить
  whitelist `noreply@jsnb.org`, alternative — попросить login через
  другой email.

### 10.8. F.account_issue — Resend аккаунт Marat'а проблемы

Это самый болезненный класс: владелец Resend = Marat (§1.2).

**Если Marat доступен:**

1. Marat логинится в Resend Dashboard, видит причину
   (suspension / billing / verification issue).
2. Если billing — оплатить.
3. Если suspension — обратиться в Resend support.
4. Восстановление: минуты или дни в зависимости от причины.

**Если Marat недоступен и Resend заблокирован:**

- Нет способа быстро восстановить OTP delivery без SES fallback.
- Эскалация: преподаватель решает с Marat'ом канал связи.
- Workaround: завести **temporary Resend account на другого
  человека** + re-verify `jsnb.org` (≈ 60 минут, требует DNS
  изменений в Cloudflare → нужен Marat для DNS).

Это **главный аргумент за немедленный SES fallback** — Track 3
больше нельзя откладывать.

### 10.9. Verify

После любого recovery:

```bash
# 1. Test OTP request через API
curl -fsS -X POST https://jsnb.org/api/v1/auth/otp/request \
  -H 'Content-Type: application/json' \
  -d '{"email":"qa+runbook@jsnb.org"}'
# Ожидание: 202 Accepted

# 2. Проверить, что письмо реально пришло (qa+runbook@... — тестовый
#    inbox дежурного)
# Опционально: full flow request + verify через UI на тестовом аккаунте

# 3. Resend Dashboard → Logs → последние 10 emails: успешные delivery,
#    нет stuck в `queued`
```

### 10.10. RTO

| Подсценарий               | RTO до stop-the-bleeding | RTO до полного recovery |
|----------------------------|--------------------------|-------------------------|
| F.outage (Resend down)     | 5 мин (выложить maintenance UI) | До восстановления Resend (часы) |
| F.backend bug              | 15 мин (rollback)               | 15–25 мин                       |
| F.sender_unverified         | 10 мин (re-verify)             | 5–60 мин (DNS propagation)      |
| F.user_specific             | N/A                            | 1–2 дня (user-side)             |
| F.account_issue (Marat доступен) | 10–30 мин                  | Зависит от Resend                |
| F.account_issue (Marat недоступен) | Часы — дни (workaround Resend account) | До завершения SES fallback |

### 10.11. Follow-up — Track 3 SES fallback (HIGH PRIORITY)

После Sprint #3 это **самый приоритетный** technical follow-up:

- Подключить **AWS SES** как secondary email provider;
- Верифицировать `noreply@jsnb.org` в SES (отдельная DNS-настройка);
- Логика в backend: try Resend → on failure → try SES → only after
  both fail → log + 503;
- Преимущества SES:
  - привязан к AWS аккаунту (а не к личному account'у),
  - управляется через Terraform,
  - дешевле Resend на масштабе;
- Недостаток: SES sandbox mode по умолчанию — требует production
  access request.

Без SES fallback Scenario F не имеет good recovery path; runbook
оперирует workaround'ами.

### 10.12. Связь с другими сценариями

- §8 Scenario D (RESEND_API_KEY leak) — частный случай F: ротация
  ключа = недолгий downtime OTP.
- §11 Scenario G (handover) — Resend account остаётся у Marat,
  поэтому он не «переезжает» вместе с AWS, что упрощает handover.

---

## 11. Scenario G — Sunset / ownership handover

**Severity:** N/A (плановое событие, не инцидент). TTD: known (дата X
объявляется заранее).

Этот сценарий **не аварийный**, а плановый. JS Notebook — учебный
проект (см. §1.1), и финансирование AWS привязано к преподавателю.
После окончания курса возможны три исхода. Этот раздел — operational
guide для каждого из них.

В отличие от Scenario A–F, тут нет «time-to-recover»; есть **дата X**
(день окончания финансирования) и подготовка к ней.

### 11.1. Три исхода

Решение принимается **минимум за 30 дней до X** между преподавателем
и Marat'ом:

| Исход         | Когда выбирать | Что происходит с инфрой |
|---------------|---------------|--------------------------|
| **G.continue** | Преподаватель продолжает оплачивать | Ничего не меняется. Этот сценарий не активируется. |
| **G.handover** | Marat (или другой owner) берёт оплату на себя | AWS account migration: либо ownership transfer существующего, либо миграция в новый аккаунт |
| **G.shutdown** | Никто не оплачивает | Graceful shutdown с архивированием артефактов; домен и Resend остаются у Marat'а |

**Default assumption до момента решения:** G.continue. Off-boarding
checklist (§11.2) всё равно стоит выполнить «на всякий случай» —
артефакты пригодятся в любом сценарии, включая будущий restart.

### 11.2. Off-boarding checklist (за 30 дней до X)

Эти шаги выполняются **независимо** от выбранного исхода. Они создают
archive, из которого можно восстановить продукт в любом сценарии,
включая re-launch через год.

#### 11.2.1. Получить подтверждение даты X

Письменно (email / chat с timestamp): «AWS финансирование прекращается
с YYYY-MM-DD». Без этого все следующие шаги — догадки.

#### 11.2.2. Снять snapshot Terraform state

```bash
# Snapshot текущего intended state — для будущей миграции
cd terraform/cloud
terraform init -reconfigure
terraform state pull > _private/archive/cloud-tfstate-$(date +%Y%m%d).json
terraform output -json > _private/archive/cloud-outputs-$(date +%Y%m%d).json

cd ../preview-cloud
terraform state pull > _private/archive/preview-tfstate-$(date +%Y%m%d).json
terraform output -json > _private/archive/preview-outputs-$(date +%Y%m%d).json
```

`_private/archive/` — локальная папка с GPG-encryption перед хранением
вне репозитория. **НЕ коммитить в git.**

#### 11.2.3. Backup RDS — manual snapshot с экспортом

```bash
# Шаг 1. Manual snapshot RDS
SNAPSHOT_ID="jsnotes-t2-db-archive-$(date +%Y%m%d)"
aws rds create-db-snapshot \
  --db-instance-identifier jsnotes-t2-db \
  --db-snapshot-identifier "$SNAPSHOT_ID"

aws rds wait db-snapshot-completed --db-snapshot-identifier "$SNAPSHOT_ID"

# Шаг 2. Export snapshot в S3 как Parquet (для долгосрочного хранения
# вне AWS зависимости)
EXPORT_TASK_ID="jsnotes-t2-export-$(date +%Y%m%d)"
aws rds start-export-task \
  --export-task-identifier "$EXPORT_TASK_ID" \
  --source-arn "arn:aws:rds:eu-north-1:867633231218:snapshot:${SNAPSHOT_ID}" \
  --s3-bucket-name jsnotes-t2-frontend \
  --iam-role-arn "arn:aws:iam::867633231218:role/rds-s3-export" \
  --kms-key-id "<KMS key id для encryption>"
# (KMS key и IAM role для export task — отдельный setup; для educational
# scope можно сделать pg_dump через ECS Exec вместо export task —
# проще, без новых ресурсов)

# Шаг 3. Альтернатива через pg_dump (без новой инфры)
aws ecs execute-command --cluster jsnotes-t2 \
  --task "$(aws ecs list-tasks --cluster jsnotes-t2 \
    --service-name jsnotes-t2-api --query 'taskArns[0]' --output text)" \
  --container api --interactive --command "/bin/sh"

# Внутри контейнера:
# pg_dump "$DATABASE_URL" -Fc -f /tmp/jsnotes-archive.dump
# # Затем скопировать /tmp/jsnotes-archive.dump наружу через S3 или
# # ECS Exec file transfer (sftp нет, можно через S3 cp при наличии
# # IAM прав на task role).
```

Сохранить дамп локально (Marat'овский диск + резервная копия).

#### 11.2.4. Архив CloudWatch Logs за последние 30 дней

```bash
# Создать export task для каждого важного log group
for LG in /ecs/jsnotes-t2-api /ecs/jsnotes-t2-migrations; do
  TASK_ID="export-$(echo "$LG" | tr '/' '-')-$(date +%Y%m%d)"
  aws logs create-export-task \
    --log-group-name "$LG" \
    --from $(date -u -v -30d +%s)000 \
    --to $(date -u +%s)000 \
    --destination jsnotes-t2-frontend \
    --destination-prefix "log-archive/${TASK_ID}/"
done

# Проверять статус
aws logs describe-export-tasks --status-code COMPLETED \
  --query 'exportTasks[].{Id:taskId,Group:logGroupName,Status:status.code}'
```

#### 11.2.5. Архив ECR images — last-good SHA'и

```bash
# Сохранить локально last-good api и ui images (последние 3 successful)
mkdir -p _private/archive/ecr

aws ecr get-login-password --region eu-north-1 | \
  docker login --username AWS --password-stdin \
  867633231218.dkr.ecr.eu-north-1.amazonaws.com

for TAG in api-sha-<latest3> ui-sha-<latest3> migrations-sha-<latest3>; do
  IMAGE="867633231218.dkr.ecr.eu-north-1.amazonaws.com/jsnotes-t2:${TAG}"
  docker pull "$IMAGE"
  docker save "$IMAGE" | gzip > "_private/archive/ecr/${TAG}.tar.gz"
done

# Альтернатива: push в личный GHCR на larchanka-training org
# (если решено сохранить deployable artifacts)
docker tag "$IMAGE" "ghcr.io/larchanka-training/jsnotes-archive:${TAG}"
docker push "ghcr.io/larchanka-training/jsnotes-archive:${TAG}"
```

#### 11.2.6. Архив Secrets Manager values

```bash
# КРИТИЧНО: значения секретов нельзя терять, но и хранить как plaintext
# нельзя. Шаги:

# Шаг 1. Получить все значения локально (через ssh tunnel или ECS Exec,
# чтобы не оставлять в shell history машины Marat'а):
SECRETS="jsnotes-t2-jwt-secret jsnotes-t2-otp-hash-secret \
         jsnotes-t2-database-url jsnotes-t2-db-migration \
         jsnotes-t2-resend-api-key jsnotes-t2-email-from"

for S in $SECRETS; do
  V=$(aws secretsmanager get-secret-value --secret-id "$S" \
    --query SecretString --output text)
  # GPG encrypt сразу, не записывать plaintext на диск
  echo "$V" | gpg --encrypt --recipient marat@... \
    > "_private/archive/secrets/${S}.gpg"
  unset V
done

# Шаг 2. Очистить shell history
history -c
unset HISTFILE
```

Хранение `_private/archive/secrets/*.gpg`:

- GPG-encrypted с приватным ключом Marat'а;
- две копии: локальный диск + offline backup (1Password / encrypted USB);
- **НЕ коммитить** даже encrypted в git (paranoid level — encryption
  алгоритмы устаревают через 10 лет).

#### 11.2.7. Архив Cloudflare DNS config

```bash
# Через Cloudflare API export текущей DNS zone:
# Dashboard → DNS → Export → BIND zone file
# Сохранить как _private/archive/cloudflare-jsnb.org-zone-YYYYMMDD.txt
```

Это нужно для:

- быстрого восстановления DNS records после future restart;
- сравнения «было / стало» если изменения произошли непреднамеренно
  (см. §8.3.7).

#### 11.2.8. Документация финального состояния

Snapshot:

- `git rev-parse HEAD` всех трёх repos (mono/api/ui) на момент X;
- скриншоты AWS Console: ECS services, RDS, CloudFront, Secrets;
- список all CloudWatch metrics за последние 30 дней (если планируется
  future restart с тем же performance baseline);
- финальная версия `_private/notes/sprint3/infra-baseline.md` с
  отметкой даты.

### 11.3. G.handover — передача владения

После §11.2 у нас есть полный archive. Handover — это перенос **живой
инфры** на нового owner'а.

#### 11.3.1. Опция A — AWS Organization invite (если new owner уже имеет AWS account)

**Простейший путь:** оставить ресурсы в текущем аккаунте `867633231218`,
добавить нового owner'а через AWS Organizations.

```text
1. Преподаватель: AWS Console → AWS Organizations → Invite account
   → email нового owner'а → Send invite.
2. New owner accepts invite через свой AWS account.
3. Преподаватель меняет billing на нового owner'а (Consolidated billing).
4. Преподаватель передаёт root credentials или создаёт IAM admin user
   для нового owner'а (предпочтительно второе — root credentials не
   передавать).
5. Marat обновляет GitHub Secrets (AWS_ACCESS_KEY_ID/SECRET) на новые
   IAM admin ключи.
6. Smoke (§2.3) → подтверждение, что pipeline работает с новыми правами.
```

**Преимущества:** минимальная миграция, ARN'ы не меняются.

**Ограничения для РФ-резидента (Marat):** AWS billing для резидентов
РФ ограничен санкциями. **Реалистично:** новый AWS account через AWS
Org нельзя зарегистрировать с РФ-billing. Поэтому:

- если new owner — Marat и он РФ-резидент → опция A не работает
  напрямую;
- альтернатива: использовать **AWS reseller через third country**
  (есть legit AWS partners в Казахстане, Турции, Сербии);
- альтернатива 2: registered legal entity (юр.лицо) **не в РФ** —
  если Marat имеет / может зарегистрировать в EU.

Без чистого решения санкционных ограничений → переход к опции B или G.shutdown.

#### 11.3.2. Опция B — Миграция в новый AWS account

Если опция A невозможна (санкции, или преподаватель хочет полностью
отвязаться от инфры):

```text
1. New owner регистрирует новый AWS account (с учётом §11.3.1
   ограничений).
2. New owner запрашивает Bedrock model access (Nova Lite/Micro) —
   это не автоматический grant, нужно ждать AWS approval (минуты —
   часы для EU аккаунтов).
3. New owner создаёт IAM admin user, передаёт credentials Marat'у.
4. Marat в new account:
   a. Запуск `infra-bootstrap.yml` → создание Terraform state bucket;
   b. Update GitHub Secrets (AWS_ACCESS_KEY_ID/SECRET, ECR registry
      ARN в `terraform/modules/backend/variables.tf`);
   c. Запуск `infra-cloud.yml` apply → новая инфра в новом account.
5. Восстановление data:
   a. Импорт RDS snapshot: `aws rds restore-db-instance-from-db-snapshot`
      из локального archive (если snapshot был копирован cross-account
      перед X) ИЛИ pg_restore через ECS Exec из локального дампа;
   b. Восстановление secrets из GPG archive (§11.2.6) → put-secret-value
      в новые Secrets Manager containers;
   c. ECR push images из локального tar.gz (или re-build из source).
6. Update Cloudflare:
   a. CloudFront domain в новом account другой (`d<new>...cloudfront.net`);
   b. Update aliases `jsnb.org`/`www.jsnb.org` на новый CloudFront domain;
   c. Re-issue ACM cert в `us-east-1` (DNS validation через Cloudflare);
   d. Update FRONTEND_ACM_CERTIFICATE_ARN GitHub variable.
7. Smoke (§2.3) → подтверждение, что full stack работает.
8. После 24 часов observations — преподаватель закрывает старый AWS
   account: `terraform destroy` (после снятия deletion_protection RDS).
```

**RTO для миграции:** 2–7 дней (зависит от Bedrock model access
approval, DNS propagation, и того, как быстро Marat выполняет шаги).

**RPO:** до времени последнего pg_dump до X (часы — дни).

#### 11.3.3. Проверка после handover

Минимально:

- jsnb.org резолвится и отвечает 200 (UI + `/api/v1/health`);
- OTP request → пользователь получает email;
- Cloud-agent работает (Bedrock invoke OK);
- `deploy-cloud.yml workflow_dispatch` успешно деплоит test PR;
- billing alerts настроены на нового owner'а.

### 11.4. G.shutdown — Graceful shutdown

Если решено не продолжать. Это **разрушительная** последовательность,
не делать без подтверждения от Marat'а и преподавателя.

#### 11.4.1. Pre-shutdown (за 7 дней до actual shutdown)

```text
1. User notification: email всем зарегистрированным + UI banner
   ("сервис закрывается DD-MM-YYYY, скачайте notebooks").
2. Self-export для пользователей: убедиться, что UI имеет export
   button для notebooks (JSON / ZIP). На 2026-06-17 — **отсутствует**.
   Tracked: `larchanka-training/dmc-1-t2-notebook-ui#82`. Это блокер
   для shutdown — должен быть закрыт до даты X.
3. Подтвердить, что §11.2 archive уже сделан.
```

#### 11.4.2. Shutdown sequence

В строгом порядке:

```bash
# Шаг 1. ECS desired_count → 0 (стоп API)
aws ecs update-service --cluster jsnotes-t2 --service jsnotes-t2-api \
  --desired-count 0
aws ecs wait services-stable --cluster jsnotes-t2 --services jsnotes-t2-api

# Шаг 2. User-facing maintenance page (через S3 + CloudFront)
aws s3 cp ./shutdown.html s3://jsnotes-t2-frontend/index.html \
  --content-type 'text/html' --cache-control 'max-age=3600'
aws cloudfront create-invalidation --distribution-id E29EW3R1X0PB5W --paths '/*'

# Шаг 3. (опционально) CloudFront disable — пользователь увидит
# CloudFront default error
aws cloudfront get-distribution-config --id E29EW3R1X0PB5W \
  --output json > /tmp/cf-config.json
# Edit Enabled: false, then update
# aws cloudfront update-distribution --id E29EW3R1X0PB5W \
#   --distribution-config file:///tmp/cf-config.json --if-match <ETag>

# Шаг 4. Final RDS snapshot ПЕРЕД destroy
FINAL_SNAPSHOT="jsnotes-t2-db-final-$(date +%Y%m%d)"
aws rds create-db-snapshot --db-instance-identifier jsnotes-t2-db \
  --db-snapshot-identifier "$FINAL_SNAPSHOT"
aws rds wait db-snapshot-completed --db-snapshot-identifier "$FINAL_SNAPSHOT"

# Шаг 5. ECR cleanup (опционально — оставить tagged images в archive)
# aws ecr batch-delete-image --repository-name jsnotes-t2 ...

# Шаг 6. Снять deletion_protection с RDS (Terraform var или прямой modify)
aws rds modify-db-instance --db-instance-identifier jsnotes-t2-db \
  --no-deletion-protection --apply-immediately

# Шаг 7. Terraform destroy (потребует confirmation)
cd terraform/cloud
terraform destroy
# Terraform спросит "Do you really want to destroy?" → yes

cd ../preview-cloud
terraform destroy
```

#### 11.4.3. Post-shutdown — что остаётся у Marat'а

- Домен `jsnb.org` (Cloudflare) — можно переключить на статическую
  «memorial page» или продать;
- Resend account (нерелевантен без сервиса, но можно держать
  бесплатный tier);
- GitHub repos (mono/api/ui) — остаются, доступны read-only любому;
- Archive (§11.2): tfstate, RDS dump, secrets.gpg, ECR images,
  Cloudflare zone, CloudWatch logs.

Это достаточно для **future restart**, если кто-то захочет вернуть
проект через любой срок.

### 11.5. G.future_restart — восстановление из archive

Допустим, через 6 месяцев решено вернуть продукт. У нас есть всё из
§11.2.

```text
1. Новый AWS account (или существующий) — настроить через §11.3.1/B.
2. Запросить Bedrock model access (Nova Lite/Micro) → ждать approval.
3. Обновить локальный clone monorepo до последнего commit на момент X
   (см. §11.2.8).
4. `terraform/cloud/variables.tf`: обновить `aws_region` если другой,
   `project` prefix если меняется.
5. `infra-bootstrap.yml` → state bucket.
6. `infra-cloud.yml` apply → создание инфры (пустая).
7. Восстановление data:
   a. `aws rds restore-db-instance-from-db-snapshot` из локального
      snapshot (если копирован) ИЛИ pg_restore через ECS Exec из
      локального дампа после первого deploy API.
   b. Restore secrets: `gpg --decrypt secret.gpg | aws secretsmanager
      put-secret-value --secret-id ... --secret-string`.
   c. ECR push images из local archive или re-build из source.
8. Update Cloudflare DNS → новый CloudFront domain.
9. Re-issue ACM cert в `us-east-1`.
10. Update FRONTEND_ACM_CERTIFICATE_ARN GitHub variable.
11. Smoke (§2.3).
12. Опубликовать UI banner "Welcome back" или silent restart.
```

**RTO для restart from cold:** 1–3 дня (с учётом Bedrock approval).

**Что НЕ восстанавливается:**

- **CloudFront distribution ID** — новый. Все логи / metrics — с нуля.
- **CloudWatch logs** — за период shutdown их не было; за период до
  shutdown — из archive (если экспортированы).
- **Bedrock approval status** — нужно запрашивать заново на новом
  account.
- **CloudFront `*.cloudfront.net` domain** — новый, не контролируется
  нами. Cloudflare aliases должны указывать на новый.
- **User sessions** — все invalidated (новый `JWT_SECRET` или восстановленный
  из archive — оба варианта валидны).

### 11.6. Что добавить follow-up'ом (для smooth handover)

Если до даты X есть время:

- **Cross-account RDS snapshot copy** — настроить регулярную копию
  snapshot'а в **личный AWS account Marat'а** (или другого backup
  account). Тогда G.shutdown сценарий перестаёт зависеть от final
  snapshot момента X.
- **GitHub Container Registry archive** — настроить параллельный push
  ECR → GHCR для всех release tags. Тогда archive ECR images не нужен
  локально.
- **Documented domain transfer procedure** — если Marat решит передать
  jsnb.org future owner'у, процедура должна быть готова.
- **Resend → SES migration** — параллельно с любым handover scenario:
  unhook OTP delivery от личного Resend account'а. Track 3 в любом
  случае HIGH PRIORITY.

### 11.7. Honest gaps

- **Cross-account RDS snapshot copy** — сейчас не настроена. Это
  значит, что архив через snapshot работает только до X; после X
  snapshot останется в старом аккаунте до его закрытия.
- **`terraform destroy` для preview environment** — не протестирован
  на реальном destroy (deletion_protection других ресурсов кроме RDS
  может вылезти).
- **Bedrock Geo profile в новом аккаунте** — predоставление inference
  profile в новом account'е может требовать manual policy attach.
  Точная процедура не задокументирована.
- **Cloudflare API token** для new owner'а — Marat остаётся владельцем
  домена, поэтому token не передаётся, но если домен **тоже** будет
  передаваться, нужен полный domain transfer playbook (out of scope
  этого runbook'а).

---

## 12. Universal verification checklist

Прогоняется после **любого** recovery (сценарии A–F) и после
G.future_restart. Если все 4 секции зелёные — recovery считается
успешным, инцидент можно закрывать.

### 12.1. Smoke (§2.3 recap)

```bash
PROD_URL="https://jsnb.org"
ALB_DNS=$(aws elbv2 describe-load-balancers --names jsnotes-t2-alb \
  --query 'LoadBalancers[0].DNSName' --output text)

# 1. UI грузится
curl -fsS -o /dev/null -w "UI:        %{http_code} %{size_download}b %{time_total}s\n" \
  "${PROD_URL}/"

# 2. API health через CloudFront
curl -fsS -w "API CF:    %{http_code} %{time_total}s\n" \
  "${PROD_URL}/api/v1/health"

# 3. ALB direct (минуя CloudFront)
curl -fsS -w "API ALB:   %{http_code} %{time_total}s\n" \
  "http://${ALB_DNS}/api/v1/health"

# 4. OTP request (auth-цепочка работает)
curl -fsS -w "OTP req:   %{http_code}\n" -X POST \
  "${PROD_URL}/api/v1/auth/otp/request" \
  -H 'Content-Type: application/json' \
  -d '{"email":"qa+runbook@jsnb.org"}'
```

**Expected:** все 4 = 200 (UI/health) или 202 (OTP), либо 429 для OTP
(rate limit — OK).

### 12.2. ECS service stable

```bash
aws ecs describe-services --cluster jsnotes-t2 --services jsnotes-t2-api \
  --query 'services[0].{TD:taskDefinition,Desired:desiredCount,Running:runningCount,Pending:pendingCount,Rollout:deployments[0].rolloutState,RolloutReason:deployments[0].rolloutStateReason}' \
  --output table
```

**Expected:**

- `Running == Desired`;
- `Pending == 0`;
- `Rollout = COMPLETED`;
- `RolloutReason` пуст или содержит «ECS deployment ... completed».

### 12.3. RDS available

```bash
aws rds describe-db-instances --db-instance-identifier jsnotes-t2-db \
  --query 'DBInstances[0].{Status:DBInstanceStatus,Storage:AllocatedStorage,Pending:PendingModifiedValues}' \
  --output table
```

**Expected:** `Status = available`, `PendingModifiedValues` пуст.

### 12.4. Свежие логи без ошибок

```bash
aws logs tail /ecs/jsnotes-t2-api --since 10m \
  --filter-pattern '?ERROR ?CRITICAL ?Exception ?Traceback' | head -50
```

**Expected:** пусто (или только known-noise patterns, документированные
отдельно).

### 12.5. End-to-end test (опционально для Sev-1)

После Sev-1 — полный test flow на тестовом аккаунте:

1. Открыть `https://jsnb.org/`.
2. Sign in: запросить OTP → проверить inbox → ввести код.
3. Создать notebook, добавить markdown + code cell.
4. Запустить code cell, проверить output.
5. AI-generate в новой cell.
6. Sign out → sign in заново.

Любой fail на шагах 1–6 — **recovery incomplete**, открыть подсценарий
повторно.

---

## 13. Postmortem template

Заполняется после **любого** Sev-1 / Sev-2 инцидента. Сохраняется в
`_private/summaries_memory/incident_<YYYY-MM-DD>_<short-slug>.md`.

Готовый пример формата — `_private/summaries_memory/sprint2_follow-up/deploy_cloud_resend_secret_rollback_14_06_2026.md`.

### Шаблон

```markdown
# Incident postmortem — <YYYY-MM-DD> — <one-line title>

## Severity и impact

- **Severity:** Sev-1 / Sev-2 / Sev-3
- **Started:** YYYY-MM-DDTHH:MM:SSZ (когда симптомы появились)
- **Detected:** YYYY-MM-DDTHH:MM:SSZ (когда дежурный узнал)
- **Mitigated:** YYYY-MM-DDTHH:MM:SSZ (когда stop-the-bleeding выполнен)
- **Resolved:** YYYY-MM-DDTHH:MM:SSZ (когда smoke зелёный)
- **Time-to-detect:** Detected − Started
- **Time-to-mitigate:** Mitigated − Detected
- **Time-to-resolve:** Resolved − Detected
- **User impact:** N пользователей, M минут downtime, какие фичи лежали

## Trigger

Что именно произошло. Один-два абзаца.

Пример:
> После merge PR #118 в `api` submodule, ECS deploy задеплоил task definition
> с обязательной production validation для `RESEND_API_KEY` и `EMAIL_FROM`.
> Эти secret values не были инициализированы в Secrets Manager.
> ECS startup завалил health check → circuit breaker откатил deployment.

## Root cause

Почему это произошло. Обычно цепочка причин:

1. Immediate cause: ...
2. Contributing factor: ...
3. Root cause (5 whys): ...

Пример:
> 1. Immediate: ECS task падает на startup → validator exception.
> 2. Contributing: `infra-cloud.yml` создаёт secret container,
>    но не ставит value automatically.
> 3. Root: код API получил production startup validation в PR #118,
>    но process для bootstrap secret values в Terraform/CI не был
>    обновлён одновременно. **Контракт между api и infra изменился
>    без согласованного PR в monorepo**.

## Detection

Как мы узнали. Время от Trigger до Detection (важно — это metric
качества observability).

Если detection реактивная (жалоба пользователя, случайно увидел красный
deploy) — это **proof для improvement в observability** (см.
runbook §3.2).

## Timeline (UTC)

```
HH:MM  Trigger event (merge / deploy / ...)
HH:MM  Detection (по какому каналу)
HH:MM  First responder ack ($whoami)
HH:MM  Diagnose started: ...
HH:MM  Hypothesis #1: ... — ruled out by ...
HH:MM  Hypothesis #2: ... — confirmed by ...
HH:MM  Mitigation действие #1: ...
HH:MM  Mitigation действие #2: ...
HH:MM  Smoke зелёный
HH:MM  Communication: "resolved" к пользователям
```

## Recovery actions

Что именно делали в порядке. Со ссылками на сценарии runbook'а.

Пример:
> 1. §6.3.1 Freeze pipeline (`gh api ... /disable`).
> 2. §6.3.3 `aws secretsmanager put-secret-value` для RESEND_API_KEY и EMAIL_FROM.
> 3. `aws ecs update-service --force-new-deployment`.
> 4. `aws ecs wait services-stable`.
> 5. §12.1 smoke verification.
> 6. §6.3.5 Unfreeze pipeline.

## Что сработало хорошо

- Что в дизайне системы / pipeline / runbook'е спасло нас от худшего исхода.
- Если runbook'а не было, что было бы хуже / медленнее.

Пример:
> - ECS circuit breaker автоматически откатил deployment → user-facing
>   impact ограничился новыми users (existing sessions работали).
> - Immutable `sha-<short>` теги — мы точно знали, какую revision вернуть.

## Что НЕ сработало

- Что должно было предотвратить инцидент и не предотвратило.
- Что замедлило detection / mitigation.

Пример:
> - Detection реактивная — узнали из жалобы user'а в чат, не из alarm.
> - Не было pre-deploy check на наличие secret values.
> - PR #118 review не поймал отсутствие parallel infra-cloud.yml update.

## Action items

Конкретные, owned, со сроком.

| # | Action | Owner | Due | Priority |
|---|--------|-------|-----|----------|
| 1 | Add pre-deploy secret presence check в `infra-cloud.yml` | DevOps | YYYY-MM-DD | P1 |
| 2 | CloudWatch alarm на `ECS-ServiceDeploymentFailed` event | DevOps | YYYY-MM-DD | P1 |
| 3 | PR review checklist: «парные изменения api ↔ infra» | Tech Lead | YYYY-MM-DD | P2 |
| 4 | Documented inventory required secrets для prod startup | DevOps | YYYY-MM-DD | P2 |

## Links

- Trigger PR: <link>
- Recovery PR (если был fix): <link>
- Slack/chat thread: <link или N/A>
- CloudWatch logs ссылки: <link или N/A>
- Этот runbook сценарий: §6 B1
```

---

## 14. Appendix A — AWS CLI shorthand

Готовый набор команд для копирования. Все используют canonical имена
из §2 / `_private/notes/sprint3/infra-baseline.md`.

### 14.1. Environment setup

```bash
export AWS_REGION=eu-north-1
export ECS_CLUSTER=jsnotes-t2
export ECS_SERVICE=jsnotes-t2-api
export TASK_FAMILY=jsnotes-t2-api
export MIG_TASK_FAMILY=jsnotes-t2-migrations
export RDS_ID=jsnotes-t2-db
export ALB_NAME=jsnotes-t2-alb
export TG_NAME=jsnotes-t2-api-tg
export FRONTEND_BUCKET=jsnotes-t2-frontend
export CLOUDFRONT_DIST_ID=E29EW3R1X0PB5W   # подтвердить list-distributions
export ECR_REGISTRY=867633231218.dkr.ecr.eu-north-1.amazonaws.com
export ECR_REPO=jsnotes-t2
export PROD_URL=https://jsnb.org
export LOG_GROUP_API=/ecs/jsnotes-t2-api
export LOG_GROUP_MIG=/ecs/jsnotes-t2-migrations
```

### 14.2. ECS

```bash
# Service state
aws ecs describe-services --cluster $ECS_CLUSTER --services $ECS_SERVICE \
  --query 'services[0].{TD:taskDefinition,Desired:desiredCount,Running:runningCount,Pending:pendingCount,Rollout:deployments[0].rolloutState}' --output table

# Service events (последние 10)
aws ecs describe-services --cluster $ECS_CLUSTER --services $ECS_SERVICE \
  --query 'services[0].events[0:10].[createdAt,message]' --output table

# Active TD details
aws ecs describe-task-definition --task-definition $(aws ecs describe-services \
  --cluster $ECS_CLUSTER --services $ECS_SERVICE \
  --query 'services[0].taskDefinition' --output text) \
  --query 'taskDefinition.containerDefinitions[0].{Image:image,Env:environment,Secrets:secrets[].name}' --output json

# List recent TD revisions
aws ecs list-task-definitions --family-prefix $TASK_FAMILY --sort DESC --max-items 10

# Force new deployment (после изменения secret value)
aws ecs update-service --cluster $ECS_CLUSTER --service $ECS_SERVICE --force-new-deployment

# Rollback к конкретной TD
aws ecs update-service --cluster $ECS_CLUSTER --service $ECS_SERVICE --task-definition <TD_ARN>

# Wait stable
aws ecs wait services-stable --cluster $ECS_CLUSTER --services $ECS_SERVICE

# Stopped tasks с reason
aws ecs list-tasks --cluster $ECS_CLUSTER --service-name $ECS_SERVICE --desired-status STOPPED \
  --query 'taskArns' --output text | \
  xargs -n1 -I{} aws ecs describe-tasks --cluster $ECS_CLUSTER --tasks {} \
    --query 'tasks[].{Stopped:stoppedReason,Code:stopCode,Exit:containers[0].exitCode}' --output json

# ECS Exec в running task (debug shell)
TASK=$(aws ecs list-tasks --cluster $ECS_CLUSTER --service-name $ECS_SERVICE \
  --desired-status RUNNING --query 'taskArns[0]' --output text)
aws ecs execute-command --cluster $ECS_CLUSTER --task "$TASK" \
  --container api --interactive --command "/bin/sh"
```

### 14.3. RDS

```bash
# Instance state
aws rds describe-db-instances --db-instance-identifier $RDS_ID \
  --query 'DBInstances[0].{Status:DBInstanceStatus,Endpoint:Endpoint.Address,Engine:Engine,LatestRestorableTime:LatestRestorableTime,Storage:AllocatedStorage,MultiAZ:MultiAZ}' --output table

# Events (последние 24ч)
aws rds describe-events --source-identifier $RDS_ID --source-type db-instance --duration 1440 \
  --query 'Events[].[Date,Message]' --output table

# Manual snapshot
aws rds create-db-snapshot --db-instance-identifier $RDS_ID \
  --db-snapshot-identifier "${RDS_ID}-manual-$(date +%Y%m%d%H%M)"

# List snapshots
aws rds describe-db-snapshots --db-instance-identifier $RDS_ID \
  --query 'sort_by(DBSnapshots, &SnapshotCreateTime)[].{Id:DBSnapshotIdentifier,Type:SnapshotType,Created:SnapshotCreateTime,Status:Status}' --output table

# PITR (см. §5.4.1 / §5.4.2 для полной процедуры)
aws rds restore-db-instance-to-point-in-time \
  --source-db-instance-identifier $RDS_ID \
  --target-db-instance-identifier "${RDS_ID}-restore-$(date +%Y%m%d%H%M)" \
  --restore-time "<YYYY-MM-DDTHH:MM:SSZ>" \
  --db-subnet-group-name jsnotes-t2-db-subnet-group \
  --no-multi-az --no-publicly-accessible \
  --db-instance-class db.t3.micro --storage-type gp3

# Modify master password (§8.3.5)
aws rds modify-db-instance --db-instance-identifier $RDS_ID \
  --master-user-password "<NEW_PASS>" --apply-immediately
```

### 14.4. Secrets Manager

```bash
# List project secrets
aws secretsmanager list-secrets --filters Key=name,Values=jsnotes-t2 \
  --query 'SecretList[].{Name:Name,ARN:ARN,LastChanged:LastChangedDate}' --output table

# Describe (без чтения value!)
aws secretsmanager describe-secret --secret-id <NAME> \
  --query '{LastChanged:LastChangedDate,Versions:VersionIdsToStages}' --output json

# Put new value
aws secretsmanager put-secret-value --secret-id <NAME> --secret-string "<VALUE>"

# Version-stage rollback (§5.4.5 / §8.3)
aws secretsmanager update-secret-version-stage --secret-id <NAME> \
  --version-stage AWSCURRENT \
  --move-to-version-id <PREVIOUS_VID> --remove-from-version-id <CURRENT_VID>
```

### 14.5. CloudFront / S3

```bash
# Find distribution by alias
aws cloudfront list-distributions \
  --query "DistributionList.Items[?contains(Aliases.Items || \`[]\`, 'jsnb.org')].Id" --output text

# Invalidation
aws cloudfront create-invalidation --distribution-id $CLOUDFRONT_DIST_ID --paths "/*"

# S3 sync UI (deploy)
aws s3 sync ./dist "s3://$FRONTEND_BUCKET" --delete
```

### 14.6. ALB

```bash
# DNS name
ALB_DNS=$(aws elbv2 describe-load-balancers --names $ALB_NAME \
  --query 'LoadBalancers[0].DNSName' --output text)
echo "$ALB_DNS"

# Target health
TG_ARN=$(aws elbv2 describe-target-groups --names $TG_NAME \
  --query 'TargetGroups[0].TargetGroupArn' --output text)
aws elbv2 describe-target-health --target-group-arn "$TG_ARN" \
  --query 'TargetHealthDescriptions[].{Target:Target.Id,State:TargetHealth.State,Reason:TargetHealth.Reason,Desc:TargetHealth.Description}' --output table
```

### 14.7. CloudWatch Logs

```bash
# Tail recent
aws logs tail $LOG_GROUP_API --since 30m

# Tail с фильтром
aws logs tail $LOG_GROUP_API --since 1h \
  --filter-pattern '?ERROR ?Exception ?Traceback'

# Insights query (async)
QID=$(aws logs start-query --log-group-name $LOG_GROUP_API \
  --start-time $(date -u -v -1H +%s) --end-time $(date -u +%s) \
  --query-string '<QUERY>' --query queryId --output text)
sleep 5
aws logs get-query-results --query-id "$QID"
```

### 14.8. ECR

```bash
# Login
aws ecr get-login-password | docker login --username AWS --password-stdin $ECR_REGISTRY

# Last 10 api images
aws ecr describe-images --repository-name $ECR_REPO --filter tagStatus=TAGGED \
  --query 'sort_by(imageDetails, &imagePushedAt)[-10:].{Tags:imageTags,Pushed:imagePushedAt}' --output table
```

---

## 15. Appendix B — CloudWatch Logs Insights queries

Сохранённые queries для типичных инцидент-диагностик. Каждую можно
запустить как:

```bash
aws logs start-query --log-group-name <GROUP> \
  --start-time $(date -u -v -1H +%s) --end-time $(date -u +%s) \
  --query-string '<QUERY-from-this-appendix>'
```

### 15.1. API startup / boot errors (для B1 config regression)

```text
filter @message like /(validation error|configuration|missing required|secret|password authentication)/
  | sort @timestamp desc
  | limit 100
```

### 15.2. Burst 5xx за последний час (для B2)

```text
filter @message like /HTTP\/1\.1" 5\d{2}/
  | parse @message /(?<status>\d{3})/
  | stats count() as cnt by bin(5m), status
  | sort @timestamp asc
```

### 15.3. LLM requests per user (для E single-user abuse)

```text
filter event = "llm.requested"
  | stats count() as requests, sum(prompt_tokens + completion_tokens) as total_tokens
        by user_id
  | sort total_tokens desc
  | limit 20
```

### 15.4. Auth failures pattern (для D security audit)

```text
filter event = "auth.failed" or @message like /(unauthorized|invalid_token|too_many_otp_attempts)/
  | stats count() as failures by bin(15m), source_ip
  | sort failures desc
  | limit 50
```

### 15.5. Slow LLM calls (для performance / E retry loop)

```text
filter event = "llm.requested" and duration_ms > 5000
  | stats avg(duration_ms) as avg_ms, max(duration_ms) as max_ms, count() as cnt by bin(5m), model_id
  | sort @timestamp asc
```

### 15.6. Migration task результаты (для A4)

```text
fields @timestamp, @message
  | filter @message like /(SUCCESSFUL|EXECUTED|FAILED|ROLLBACK|Liquibase command 'update' was executed)/
  | sort @timestamp desc
  | limit 50
```

Запускать против `$LOG_GROUP_MIG`.

### 15.7. Secret-related startup failures (catch-all для B1)

```text
filter @message like /(NoCredentialsError|ResourceInitializationError|AccessDenied|GetSecretValue)/
  | stats count() as cnt by bin(15m), @message
  | sort cnt desc
  | limit 20
```

### 15.8. Rate-limit hits (для E + D recovery verification)

```text
filter @message like /(too_many_otp|429|rate_limit)/
  | stats count() as cnt by bin(5m), @message
  | sort @timestamp asc
```

---

## 16. Appendix C — App-level kill switches

Один блок со всеми available kill switches. Использовать при mass
abuse / cost spike / known-bad code в production.

### 16.1. LLM Cloud-agent off

**Level 1 — env var (target/future, НЕ работает сегодня):**

> ⚠ 2026-06-17 confirmed: env-флага `LLM_CLOUD_AGENT_ENABLED` нет в
> коде и в active TD. Этот уровень — для будущей имплементации. В
> реальном инциденте сегодня используйте **Level 2** ниже.

```bash
# Требует, чтобы код API проверял LLM_CLOUD_AGENT_ENABLED. Сейчас НЕ
# проверяет — нужен PR в api/ и terraform/ (см. §9.8 HIGH PRIORITY).

ACTIVE_TD=$(aws ecs describe-services --cluster $ECS_CLUSTER --services $ECS_SERVICE \
  --query 'services[0].taskDefinition' --output text)

NEW_TD_JSON=$(aws ecs describe-task-definition --task-definition "$ACTIVE_TD" \
  --query 'taskDefinition' --output json | \
  jq '.containerDefinitions[0].environment += [{"name":"LLM_CLOUD_AGENT_ENABLED","value":"false"}]
      | del(.taskDefinitionArn, .revision, .status, .requiresAttributes, .compatibilities, .registeredAt, .registeredBy)')

KILL_TD=$(echo "$NEW_TD_JSON" | aws ecs register-task-definition --cli-input-json file:///dev/stdin \
  --query 'taskDefinition.taskDefinitionArn' --output text)

aws ecs update-service --cluster $ECS_CLUSTER --service $ECS_SERVICE \
  --task-definition "$KILL_TD" --force-new-deployment
```

Откат — apply Terraform (восстановит env без LLM_CLOUD_AGENT_ENABLED).

**Level 2 — IAM revoke (hard kill, гарантированно):**

```bash
# Удалить Bedrock invoke policy
aws iam delete-role-policy --role-name jsnotes-t2-ecs-task \
  --policy-name jsnotes-t2-bedrock-invoke

aws ecs update-service --cluster $ECS_CLUSTER --service $ECS_SERVICE --force-new-deployment
```

Откат — `terraform apply` (восстановит policy из
`terraform/modules/backend/bedrock.tf`).

### 16.2. ECS desired_count → 0 (full API shutdown)

```bash
# Использовать только для G.shutdown или extreme Sev-1.
# Полностью останавливает API: UI работает (CloudFront/S3), но любой
# /api/v1/* вызов → 502.

aws ecs update-service --cluster $ECS_CLUSTER --service $ECS_SERVICE --desired-count 0
aws ecs wait services-stable --cluster $ECS_CLUSTER --services $ECS_SERVICE

# Восстановить:
aws ecs update-service --cluster $ECS_CLUSTER --service $ECS_SERVICE --desired-count 1
aws ecs wait services-stable --cluster $ECS_CLUSTER --services $ECS_SERVICE
```

### 16.3. CloudFront origin disable / maintenance page

```bash
# Подменить S3 index.html на maintenance page
aws s3 cp ./maintenance.html s3://$FRONTEND_BUCKET/index.html \
  --content-type 'text/html' --cache-control 'max-age=60'
aws cloudfront create-invalidation --distribution-id $CLOUDFRONT_DIST_ID --paths '/' '/index.html'

# Восстановить — re-deploy UI через `aws s3 sync` (см. §14.5)
```

### 16.4. Block single user (для E.single-user abuse)

> ⚠ **Архитектурный gap (2026-06-17):** колонки `disabled_at` в
> `users.users` нет (см. `api/app/modules/auth/models/user.py`).
> Изолированная per-user блокировка **не доступна** без code change.
> Tracked: `larchanka-training/dmc-1-t2-notebook-api#73`. Подробно — §9.4.1.

Доступные workaround'ы:

- §9.4.2 — Cloud-agent kill switch (если abuse именно по LLM-пути,
  затрагивает всех Cloud-agent users одинаково);
- §8.3.3 — Rotate JWT_SECRET (force re-login для всех; затем bot
  не пройдёт OTP — если он бот);
- Hard delete user row (необратимо удаляет user + notebooks через
  CASCADE; только при подтверждённом bot'е):

```bash
TASK=$(aws ecs list-tasks --cluster $ECS_CLUSTER --service-name $ECS_SERVICE \
  --desired-status RUNNING --query 'taskArns[0]' --output text)
aws ecs execute-command --cluster $ECS_CLUSTER --task "$TASK" \
  --container api --interactive --command "/bin/sh"
# psql "$DATABASE_URL" -c "DELETE FROM users.users WHERE id = '<USER_UUID>';"
```

Follow-up для нормальной реализации — §9.8: миграция + middleware.

### 16.5. Freeze CI/CD pipeline

```bash
# Деплой pipeline disable (см. §6.3.1)
gh api -X PUT \
  /repos/larchanka-training/dmc-1-t2-notebook-mono/actions/workflows/deploy-cloud.yml/disable

# Restore
gh api -X PUT \
  /repos/larchanka-training/dmc-1-t2-notebook-mono/actions/workflows/deploy-cloud.yml/enable
```

### 16.6. Bedrock model access revoke (account-level kill, ultimate)

```bash
# Используется только если §16.1 не работает и нужен абсолютный stop.
# Действие на уровне account, не region.

# AWS Console → Bedrock → Model access → Manage model access →
# Снять checkbox с Nova Lite / Nova Micro → Save changes.
# Любой Bedrock invoke на любой model → AccessDeniedException.

# Восстановить — там же re-enable (обычно мгновенно для уже approved models).
```

Это требует **AWS account owner** (преподаватель) — Marat без console
access не сможет.

---

## 17. Appendix D — Terraform state DR

Terraform state — **скрытая критическая dependency** почти для всех
recovery-сценариев (failover региона, переименование restored
instance'а, rollback IAM-policy). Если state потерян или lock застрял —
большинство процедур runbook'а блокируются.

**Текущая конфигурация (из `terraform/cloud/backend.tf`):**

- Backend: S3 bucket `dmc-1-t2-notebook-terraform-state`;
- Locking: native S3 `use_lockfile = true` (Terraform ≥ 1.10), **нет
  DynamoDB**;
- Versioning bucket: enabled (можно восстановить version).

### 17.1. Сценарий: state objet удалён / повреждён

#### Identify

```bash
cd terraform/cloud
terraform init 2>&1 | head -20
# Признаки: "Failed to load state" / "no such file" / unexpected EOF.

# Проверить версии в bucket'е
aws s3api list-object-versions \
  --bucket dmc-1-t2-notebook-terraform-state \
  --prefix cloud/terraform.tfstate \
  --query 'Versions[].{VersionId:VersionId,LastModified:LastModified,Size:Size,IsLatest:IsLatest}' \
  --output table
```

#### Recovery

```bash
# Шаг 1. Найти последнюю known-good version (не текущая если она broken)
GOOD_VID="<copy from list-object-versions>"

# Шаг 2. Восстановить версию объекта (скопировать в "текущую")
aws s3api copy-object \
  --bucket dmc-1-t2-notebook-terraform-state \
  --copy-source "dmc-1-t2-notebook-terraform-state/cloud/terraform.tfstate?versionId=${GOOD_VID}" \
  --key cloud/terraform.tfstate

# Шаг 3. Verify
cd terraform/cloud
terraform init -reconfigure
terraform plan
# Plan должен показать no-op или минимальный дрейф.
```

#### RTO

5–15 минут.

### 17.2. Сценарий: native S3 lock застрял

#### Identify

```bash
terraform plan 2>&1 | head -10
# "Error: Error acquiring the state lock" / "ConditionalCheckFailedException"
# или "lock file ... exists".
```

#### Recovery

```bash
# Шаг 1. Проверить, нет ли активного workflow (infra-cloud.yml)
gh run list --workflow infra-cloud.yml --limit 5 --json status,conclusion,createdAt
# Если есть running — подождать.

# Шаг 2. Если ничего активного — найти lock file
aws s3 ls "s3://dmc-1-t2-notebook-terraform-state/cloud/" --recursive | grep tflock

# Шаг 3. Force-unlock через Terraform (предпочтительно)
cd terraform/cloud
terraform force-unlock <LOCK_ID_from_error_message>
# (LOCK_ID — UUID из сообщения об ошибке)

# Шаг 4. Если force-unlock не работает — manual delete lock file
aws s3 rm "s3://dmc-1-t2-notebook-terraform-state/cloud/terraform.tfstate.tflock"
```

#### RTO

2–5 минут.

> ⚠ **Никогда** не delete'ить lock file во время реально работающего
> apply из другого окружения. Это может оставить state в inconsistent
> состоянии. Сначала убедиться через `gh run list`, что нет активных
> workflow'ов.

### 17.3. Сценарий: state bucket удалён

Самый худший случай.

#### Recovery (если bucket был versioned — наш случай)

```bash
# Восстановление bucket'а через AWS Support (если bucket был удалён <30 дней назад).
# Иначе — recovery невозможен, нужно re-bootstrap state с нуля
# (`infra-bootstrap.yml` workflow_dispatch) + ручной terraform import
# всех существующих ресурсов.
```

RTO в случае без бэкапа state'а:

- 4–8 часов (manual import всех ресурсов через `terraform import`);
- Альтернатива: `terraform destroy` оставшихся ресурсов + `apply`
  заново → data loss (RDS, secrets — пропадают).

### 17.4. Follow-up

- **Cross-region replication state bucket'а** → копия в `eu-west-1`
  как safety net против регионального outage / accidental delete.
  Cost ≈ $1/мес.
- **State backup в отдельный AWS account** Marat'а (если будет в
  G.handover scope).
- **Tag state bucket as critical** + S3 Object Lock (если возможно)
  для защиты от accidental delete.

---

> Конец черновика runbook'а. Структура полная: Prerequisites + §1–4
> общая часть + §5–11 сценарии A–G + §12 verification + §13 postmortem
> + §14–17 appendices A/B/C/D. Шаг 9 — self-review целиком,
> финальные правки. Шаг 10 — перенос в `docs/runbook.md` через feature
> branch + PR.
