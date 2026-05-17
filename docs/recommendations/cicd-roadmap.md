# CI/CD Roadmap для JS-Notebook

> Документ — справочник «что у нас не хватает в CI/CD, зачем это, где
> настраивается, в каком порядке внедрять». Ориентирован на DevOps-новичка,
> который знаком с Python/FastAPI на среднем уровне и впервые работает с
> GitHub Actions, Docker, AWS.

---

## 0. Роль DevOps в этом проекте (что от вас ждут)

### Зона ответственности

| Слой | Что делать |
|---|---|
| **Локальная среда** | `docker-compose.yaml`, скрипты `start-services.sh`, инструкции по hosts, сертификатам |
| **CI (GitHub Actions)** | Workflow-ы lint/test/build для api, ui, моно; required checks; кеширование; защита веток |
| **Реестр образов** | GHCR (`ghcr.io`) — публикация образов API/UI с правильными тегами |
| **Артефакты** | Хранение coverage, dist, bundle-size в Actions artifacts |
| **Секреты** | `GH_PAT`, токены реестров, OAuth secrets, DB URL — через GitHub Secrets и Environments |
| **Деплой (позже AWS)** | ECS Fargate / EC2 + RDS PostgreSQL, инфраструктура как код (Terraform / CDK) |
| **Observability** | Логи (CloudWatch/Loki), метрики (Prometheus/CloudWatch), алерты, healthcheck |
| **Security** | Trivy/SBOM сканы, ротация секретов, branch protection, ограничение `permissions:` |

### Что **не** ваша зона (но полезно понимать)

- Бизнес-логика FastAPI (auth, sync, LLM-proxy) — это backend-разработчик.
- React-компоненты, Reatom-сторы, sandbox JS — это frontend-разработчик.
- Тестовая стратегия (что покрывать) — это QA, но автоматизация запуска ваша.

### Чем DevOps занимается в этом проекте на каждом этапе

**Стадия 0 (сейчас — MVP скаффолд):**
1. Починить сломанные workflow-ы (`docker-compose.yml`).
2. Стабилизировать локальный запуск (`docker compose up` должен работать с нуля).
3. Завести минимальные required checks в репозиториях.
4. Поднять GHCR + первый publish-job для api/ui образов.
5. Документировать `.env.example` и хранение секретов.

**Стадия 1 (появляется backend-логика):**
6. Добавить интеграционный smoke-тест (compose up → curl `/health`).
7. Подключить Alembic-миграции в CI (`alembic upgrade head` на временной БД).
8. Поднять staging-окружение (одна EC2 + RDS, или Fly.io/Render).
9. Завести deploy-workflow с ручным approve.
10. Сделать rollback-стратегию (предыдущий тег + `docker compose up`).

**Стадия 2 (production):**
11. AWS: VPC, RDS, ECS/Fargate (или EKS), ALB, ACM-сертификаты, Route53.
12. Infrastructure as Code (Terraform или AWS CDK).
13. Observability: CloudWatch Logs, метрики, алерты, runbook.
14. Security: WAF, Secrets Manager, IAM-роли через OIDC.
15. CDN для статики UI (CloudFront или S3-website + CloudFront).
16. Backup-стратегия БД, disaster recovery план.

### Хард-скиллы, которые стоит подтянуть в этом порядке

1. **YAML + GitHub Actions** (1–2 недели): синтаксис, `jobs`, `steps`,
   `needs`, `if`, `matrix`, `secrets`, `vars`, `permissions`, `concurrency`.
2. **Docker** (2 недели): multi-stage builds, layer caching, `.dockerignore`,
   healthchecks, non-root users, `docker compose` для интеграции.
3. **Bash** (постоянно): без него никуда — все workflow-шаги это bash.
4. **AWS базовые сервисы** (2–4 недели): IAM, VPC, EC2, RDS, S3, ECS/Fargate,
   CloudWatch, Route53, ACM. Лучше начать с курса Cloud Practitioner или
   Solutions Architect Associate.
5. **Terraform** (2–3 недели): на этапе AWS.
6. **Linux** (постоянно): systemd, journalctl, файрволы, networking.

---

## 1. Чего НЕ хватает в CI/CD — построчный разбор

Ниже — каждый из 11 пунктов с ответами: *что это, зачем, где настроить, как
выглядит, в каком порядке*.

---

### 1.1. Нет publish-job для образов

**Что.** Сейчас оба workflow заканчиваются на `docker build -t … .`.
После того как job закончился, образ удаляется вместе с runner-ом. Нигде во
внешнем мире его нет.

**Зачем нужно публиковать.**
- Чтобы деплой-job (или человек на сервере) мог `docker pull` готовый образ.
- Чтобы прод-сервер не пересобирал образ с нуля.
- Чтобы можно было быстро откатиться: `docker pull <old-tag>` + restart.
- Чтобы образы были иммутабельны (важно для воспроизводимости).

**Где настроить.** Внутри уже существующих `.github/workflows/api-ci.yml`
и `ui-ci.yml`, в job `Docker Build`. Идеально — выделить отдельный job
`publish`, который запускается **только на `main`** и на `tags: ['v*']`,
а PR-сборки остаются без push (как сейчас).

**Куда публиковать.** Рекомендую **GHCR** (`ghcr.io/<org>/<image>`):
- встроено в GitHub, не надо отдельной учётки;
- логин через `GITHUB_TOKEN`;
- private видимость наследуется от репозитория.

**Шаги (в python-псевдокоде workflow):**

```yaml
permissions:
  contents: read
  packages: write          # ← без этого push в ghcr.io упадёт 403
  id-token: write          # ← для cosign / OIDC в AWS

steps:
  - uses: actions/checkout@<sha>
    with: { submodules: recursive, token: ${{ secrets.GH_PAT }} }

  - uses: docker/setup-qemu-action@<sha>     # multi-arch (опц.)
  - uses: docker/setup-buildx-action@<sha>   # buildkit с кешем

  - uses: docker/login-action@<sha>
    with:
      registry: ghcr.io
      username: ${{ github.actor }}
      password: ${{ secrets.GITHUB_TOKEN }}

  - id: meta
    uses: docker/metadata-action@<sha>
    with:
      images: ghcr.io/${{ github.repository_owner }}/js-notebook-api
      tags: |
        type=ref,event=branch              # main → :main
        type=ref,event=pr                  # PR-25 → :pr-25
        type=sha,prefix=sha-,format=short  # → :sha-1a2b3c4
        type=semver,pattern={{version}}    # v1.2.3 → :1.2.3
        type=raw,value=latest,enable={{is_default_branch}}

  - uses: docker/build-push-action@<sha>
    with:
      context: ./api
      push: ${{ github.event_name != 'pull_request' }}
      tags: ${{ steps.meta.outputs.tags }}
      labels: ${{ steps.meta.outputs.labels }}
      cache-from: type=gha,scope=api
      cache-to: type=gha,mode=max,scope=api
```

**Итог.** После merge в `main` появится
`ghcr.io/<org>/js-notebook-api:main` и `:sha-<short>`. На сервере:

```bash
docker pull ghcr.io/<org>/js-notebook-api:main
docker stop js-notebook-api && docker rm js-notebook-api
docker run -d --name js-notebook-api --env-file /opt/notebook/.env -p 8000:8000 \
  ghcr.io/<org>/js-notebook-api:main
```

---

### 1.2. Нет deploy-job

**Что.** В `api/docs/ci-cd.md` деплой описан текстом: «зайдите на сервер,
сделайте docker pull и run». В CI этой автоматизации нет.

**Зачем автоматизировать.** Ручной деплой = человек забыл, человек сделал
`run` без `--restart`, человек оставил старый контейнер, человек залогинился
ssh-ключом коллеги. Автоматика убирает эти классы ошибок.

**Где настроить.** Отдельный workflow `.github/workflows/deploy.yml`,
который триггерится:

```yaml
on:
  push: { branches: [main] }            # auto-deploy на staging
  workflow_dispatch:                     # ручной trigger
    inputs:
      environment:
        type: choice
        options: [staging, production]
      tag:
        description: 'Image tag, например sha-1a2b3c4 или v1.2.3'
        default: 'main'
```

**Варианты целевой платформы (от простого к сложному):**

| Платформа | Сложность | Когда выбирать |
|---|---|---|
| **VPS + ssh + docker compose** | ⭐ | Учебный проект, до 100 пользователей |
| **Fly.io / Render / Railway** | ⭐⭐ | MVP, не хочется возиться с AWS |
| **AWS EC2 + ssh** | ⭐⭐ | Учитесь AWS пошагово |
| **AWS ECS Fargate** | ⭐⭐⭐ | Прод, autoscale, без managed-серверов |
| **AWS EKS (Kubernetes)** | ⭐⭐⭐⭐ | Команда из 5+, мульти-сервисная архитектура |

**Самый простой пример — SSH на VPS:**

```yaml
- uses: appleboy/ssh-action@<sha>
  with:
    host: ${{ secrets.SSH_HOST }}
    username: ${{ secrets.SSH_USER }}
    key: ${{ secrets.SSH_PRIVATE_KEY }}
    script: |
      set -euo pipefail
      cd /opt/notebook
      echo "${{ secrets.GITHUB_TOKEN }}" | docker login ghcr.io -u ${{ github.actor }} --password-stdin
      IMAGE_TAG=${{ inputs.tag || github.sha }} docker compose pull
      IMAGE_TAG=${{ inputs.tag || github.sha }} docker compose up -d
      docker image prune -f
```

`docker-compose.prod.yaml` на сервере должен использовать `image:` вместо
`build:`:

```yaml
services:
  api:
    image: ghcr.io/<org>/js-notebook-api:${IMAGE_TAG:-main}
  frontend:
    image: ghcr.io/<org>/js-notebook-ui:${IMAGE_TAG:-main}
```

**После деплоя — smoke-тест и нотификация:**

```yaml
- run: |
    sleep 5
    curl -fsS https://api.notebook.com/api/v1/health | grep -q '"status":"ok"'
- if: failure()
  uses: slackapi/slack-github-action@<sha>
  with: { payload: '{"text":"Deploy failed: ${{ github.sha }}"}' }
```

---

### 1.3. Нет тегирования

**Что.** Сейчас образ только `js-notebook-api:${{ github.sha }}`.
Это полный SHA, его никто не запомнит, и он живёт только в job.

**Зачем нужно несколько тегов.**

| Тег | Смысл | Пример |
|---|---|---|
| `:sha-1a2b3c4` | Точная иммутабельная версия — для rollback | для каждого build |
| `:main` | «Текущий main» — для staging | при merge в main |
| `:edge` | Алиас main или nightly | опц. |
| `:pr-25` | Версия для preview-окружения PR | при PR |
| `:1.2.3` (SemVer) | Релиз — для production | при `git tag v1.2.3` |
| `:1.2` и `:1` | Минорный/мажорный pinning | при release |
| `:latest` | Обычно = последний SemVer | при release |

**Где настроить.** `docker/metadata-action` (см. пункт 1.1) генерирует
все эти теги автоматически по правилам.

**Правило.** На production-сервере используйте **только** `:sha-<short>` или
`:1.2.3`. Никогда `:latest` и `:main` напрямую в prod — потеряете
воспроизводимость и не сможете откатиться.

**Как сделать release.** В монорепо:

```bash
git tag v0.1.0 -m "First MVP release"
git push origin v0.1.0
```

→ workflow ловит `tags: ['v*.*.*']` → собирает образы → пушит как
`:0.1.0`, `:0.1`, `:latest`.

---

### 1.4. Нет кеша билда

**Что.** Каждый Docker-билд начинается с нуля: тянет base image, ставит pnpm,
ставит зависимости. На pnpm+Vite — 2–4 минуты на ровном месте.

**Зачем.** GitHub Actions runner — это новая виртуалка на каждый job.
Без кеша вы платите эти 2–4 минуты за каждый PR.

**Где настроить.** В `docker/build-push-action`:

```yaml
cache-from: type=gha,scope=ui
cache-to: type=gha,mode=max,scope=ui
```

- `type=gha` — кеш в GitHub Actions cache backend (10 ГБ на репо бесплатно).
- `scope=ui` / `scope=api` — отдельные кеши для разных образов, иначе будут
  топтать друг друга.
- `mode=max` — кешировать все промежуточные слои (а не только финальные).

**Дополнительно для pnpm**: `actions/setup-node@... { cache: pnpm }` —
кеширует `~/.local/share/pnpm/store`, ускоряет `pnpm install` с 60 сек
до 5–10 сек. Это уже включено в моно `ui-ci.yml`, проверьте, что есть в
submodule CI тоже.

**Что измерять.** До-после: время job в `Actions → Workflow run`.
Должно упасть в 2–4 раза на повторных билдах.

---

### 1.5. Нет матрицы платформ (`linux/amd64,linux/arm64`)

**Что.** Образ сейчас собирается только под архитектуру runner-а
(GitHub Actions Linux = amd64). На Mac M1/M2/M3 и AWS Graviton (arm64)
образ запустится через эмуляцию (медленно) или не запустится.

**Зачем multi-arch.**
- Локальная разработка на Mac M-series без эмуляции.
- AWS Graviton (arm64) дешевле x86 на ~20%, многие команды переходят.
- Raspberry Pi и edge-сценарии.

**Где настроить.**

```yaml
- uses: docker/setup-qemu-action@<sha>          # эмуляция arm64 на amd64-runner
- uses: docker/setup-buildx-action@<sha>
- uses: docker/build-push-action@<sha>
  with:
    platforms: linux/amd64,linux/arm64
    push: true
```

**Цена.** arm64-сборка через QEMU на amd64-runner медленнее в ~2 раза.
Альтернатива: GitHub Actions с нативными arm64-runner-ами (платно для
public/free org, либо self-hosted).

**Прагматично.** На MVP-этапе можно оставить только `linux/amd64` и
включить arm64, когда реально понадобится. Не считается критическим
пробелом.

---

### 1.6. Нет `concurrency`

**Что.** Без блока `concurrency` каждый push в ту же ветку (или каждый
коммит в той же PR) запускает новую сборку, не отменяя предыдущую.
Результат: 3 параллельных билда на 3 коммита подряд = 3× CPU-минут.

**Зачем.** Сэкономить минуты GitHub Actions (free org — 2000 мин/мес),
не нагружать кеш одновременно, избежать race-условий при пуше образов.

**Где настроить.** На уровне workflow (или job) — отдельный блок верхнего
уровня:

```yaml
name: API CI
on: [push, pull_request]

concurrency:
  group: api-ci-${{ github.workflow }}-${{ github.ref }}
  cancel-in-progress: true   # отменить предыдущие runs в той же группе
```

**Как формировать `group`.**

| Группа | Эффект |
|---|---|
| `${{ github.workflow }}-${{ github.ref }}` | По одному build на ветку |
| `${{ github.workflow }}-${{ github.event.pull_request.number }}` | По одному build на PR |
| `deploy-${{ inputs.environment }}` | По одному deploy на environment (staging/prod не пересекаются) |

**Когда НЕ ставить `cancel-in-progress: true`.**
- Для deploy в production — не отменять, иначе можно прервать
  выкатку посередине и оставить кластер в полуразвалившемся состоянии.
- Для release-workflow по тегу — каждый тег важен.

**Где включить в нашем проекте.** В трёх файлах сразу:
`api-ci.yml`, `ui-ci.yml`, `docker-compose.yml` (после починки опечаток),
и в будущем `deploy.yml`.

**Чек, что работает.** Сделать два пуша подряд в feature-branch, открыть
вкладку Actions: первый run должен быть «Cancelled», второй — «In progress».

---

### 1.7. Сломан `docker-compose.yml` workflow

Уже исправлено пользователем — пропускаем.

После починки добавьте сразу: `concurrency`, smoke-тест после
`docker compose up -d`:

```yaml
- name: Smoke test
  run: |
    docker compose up -d
    for i in {1..30}; do
      if curl -fsS http://localhost:8000/api/v1/health; then exit 0; fi
      sleep 2
    done
    docker compose logs
    exit 1
```

---

### 1.8. Нет required-checks-конфига как кода

**Что.** Сейчас branch protection / required status checks настраиваются
через GitHub UI (Repository → Settings → Rules). Это «настройки кликами»,
их легко забыть, нельзя ревьюить, нельзя восстановить после случайного
сноса.

**Зачем как код.** Воспроизводимость, ревью, история изменений. Если
кто-то снимет required-check и зальёт сломанный код в `main`, вы это
увидите в git-логе.

**Где настроить.** Три способа:

1. **GitHub CLI скрипт** (`scripts/setup-branch-protection.sh`):

   ```bash
   gh api repos/<org>/<repo>/rulesets \
     --method POST \
     --header "Accept: application/vnd.github+json" \
     --input ruleset.json
   ```

   `ruleset.json` коммитится в репо.

2. **Terraform** (`github` provider) — для серьёзной IaC-настройки:

   ```hcl
   resource "github_repository_ruleset" "main" {
     name        = "Protect main"
     target      = "branch"
     enforcement = "active"
     conditions { ref_name { include = ["~DEFAULT_BRANCH"] } }
     rules {
       required_status_checks {
         required_check { context = "API CI / Lint" }
         required_check { context = "API CI / Test" }
         required_check { context = "API CI / Docker Build" }
       }
       pull_request { required_approving_review_count = 1 }
     }
   }
   ```

3. **`.github/workflows/setup-repo.yml`** — workflow, который при ручном
   запуске применяет настройки через `gh api`.

**Прагматично для учебного проекта.** Начните с CLI-скрипта в `scripts/`,
запускайте руками. К Terraform — когда появится прод.

**Подводный камень.** В монорепо с `paths`-фильтрами PR, который трогает
только `docs/`, **не запускает** `api-ci.yml` или `ui-ci.yml`. Required
checks при этом будут висеть в статусе «Expected — waiting for status».
Решения:
- Убрать `paths`-фильтры (всё гонять всегда — дорого).
- Добавить «always-green» job без фильтров, который и будет required.
- Использовать action типа `dorny/paths-filter` + skip-job, который
  репортит success при отсутствии релевантных изменений.

---

### 1.9. Нет SBOM / cosign / Trivy сканов

**Что.**

| Термин | Что значит |
|---|---|
| **SBOM** (Software Bill of Materials) | Список всех зависимостей и их версий в образе. Формат SPDX или CycloneDX |
| **Trivy** | Сканер уязвимостей: смотрит CVE в base image, в pip/npm-пакетах |
| **cosign** | Подпись образа криптографическим ключом (или keyless через OIDC). Гарантирует, что образ собран именно вашим CI |

**Зачем.**
- SBOM нужен для compliance (SOC2, ISO) и инцидент-ответа (когда появится
  новый CVE — быстро увидите, что вы подвержены).
- Trivy ловит «известные дыры» до прода. Падение build на HIGH/CRITICAL
  CVE заставляет разработчика обновить зависимость.
- cosign защищает от подмены образа в registry (атака supply chain).

**Где настроить.**

```yaml
- name: Trivy scan
  uses: aquasecurity/trivy-action@<sha>
  with:
    image-ref: ghcr.io/<org>/js-notebook-api:${{ github.sha }}
    severity: HIGH,CRITICAL
    exit-code: 1
    ignore-unfixed: true   # не падать на CVE без патча

- name: Generate SBOM
  uses: anchore/sbom-action@<sha>
  with: { image: ghcr.io/<org>/js-notebook-api:${{ github.sha }}, format: spdx-json }

- name: Cosign sign
  uses: sigstore/cosign-installer@<sha>
- run: cosign sign --yes ghcr.io/<org>/js-notebook-api@${{ steps.build.outputs.digest }}
  env: { COSIGN_EXPERIMENTAL: "1" }
```

**Прагматично.** На MVP-этапе подключайте по очереди:
1. Trivy с `exit-code: 0` (только репорт, не блокирует).
2. SBOM как artifact (для будущих compliance-задач).
3. cosign — когда будет prod-кластер.

---

### 1.10. Нет интеграционного smoke-теста

**Что.** Самый дешёвый и самый полезный тест: «после `docker compose up -d`
все сервисы поднимаются, healthcheck отвечает 200».

**Зачем.** Ловит реальные интеграционные баги:
- API не подключается к Postgres (не тот пароль, не та сеть).
- Frontend образ не находит API из-за CORS / proxy.
- Healthcheck сломан (упал в Dockerfile, не доходит до приложения).
- `.env`-переменная пропала из compose.

Без него все unit-тесты могут быть зелёные, а `docker compose up`
ломаться при каждом merge.

**Где настроить.** В `.github/workflows/docker-compose.yml` после
`docker compose build`:

```yaml
- name: Up
  run: docker compose up -d

- name: Wait for API
  run: |
    for i in {1..30}; do
      if curl -fsS http://localhost:8000/api/v1/health; then
        echo "API ready"; exit 0
      fi
      sleep 2
    done
    docker compose ps
    docker compose logs api
    exit 1

- name: Wait for UI
  run: |
    for i in {1..30}; do
      if curl -fsS http://localhost:3000/ | grep -q '<div id="root">'; then
        echo "UI ready"; exit 0
      fi
      sleep 2
    done
    docker compose logs frontend
    exit 1

- name: Down
  if: always()
  run: docker compose down -v
```

**Усложнение (на следующем шаге).** Запустить Playwright-тест на ту же
поднятую систему:

```yaml
- run: pnpm exec playwright install --with-deps chromium
- run: pnpm exec playwright test e2e/
```

---

### 1.11. Нет workflow для UI submodule

См. отдельный документ `docs/recommendations/ui-submodule-ci.md` —
подробно описаны структура и наполнение.

---

## 2. Шаги для DevOps в этом проекте (порядок внедрения)

### Этап A — стабилизация (1–2 недели)

1. ✅ Починить `docker-compose.yml` workflow (опечатки).
2. Добавить `concurrency` во все три workflow моно.
3. Добавить `cache-from: type=gha` и `setup-buildx` в Docker-сборки.
4. Перевести `actions/checkout` на pin по SHA (где ещё не сделано).
5. Завести `scripts/setup-branch-protection.sh` с required checks.
6. Очистить `.gitignore` (см. ниже пункт «git артефакты»).

### Этап B — публикация образов (1 неделя)

7. Добавить permission `packages: write` в job, который пушит.
8. Создать `publish` job с `docker/login-action` → `ghcr.io`.
9. Подключить `docker/metadata-action` для нормальных тегов.
10. Опубликовать первый образ вручную (push в `main`), проверить, что
    `docker pull ghcr.io/<org>/js-notebook-api:main` работает.

### Этап C — интеграционный smoke (1 неделя)

11. Расширить `docker-compose-ci.yml` smoke-тестом healthcheck.
12. Добавить `if: failure() docker compose logs` для дебага.

### Этап D — staging-окружение (2 недели)

13. Поднять VPS (Hetzner / DigitalOcean) или Fly.io.
14. Завести `docker-compose.prod.yaml` с `image:` (без `build:`).
15. Положить prod `.env` на сервер.
16. Создать GitHub Environment `staging` с required reviewers и secrets.
17. Workflow `deploy.yml` на `push: main` → ssh-deploy → smoke-test.

### Этап E — production и AWS (5–8 недель)

18. AWS account, IAM-пользователь и OIDC-доверие к GitHub Actions.
19. VPC, subnets, security groups (Terraform или CDK).
20. RDS PostgreSQL Multi-AZ.
21. ECR (или продолжать GHCR + pull-secret).
22. ECS Fargate task definitions для api и ui.
23. ALB + ACM-сертификат + Route53.
24. CloudWatch Logs + базовые алерты (CPU, latency, 5xx).
25. Secrets Manager для prod-секретов, не `.env` на инстансе.
26. Backup-стратегия RDS + smoke-test восстановления.
27. Runbook: «что делать при падении prod».

### Этап F — операционная зрелость

28. Trivy + SBOM в pipeline.
29. cosign-подпись + verify на pull.
30. Blue/Green или Canary deployment.
31. Distributed tracing (OpenTelemetry → CloudWatch X-Ray).
32. Регулярные DR-учения (раз в квартал восстанавливать из бэкапа).

---

## 3. Конкретно про Docker в GitHub Actions (детально)

### 3.1. Что вам нужно понять «как работает»

1. **Каждый job — новый виртуальный Linux**. Все установки в job не
   переносятся в следующий job без artifacts/cache.
2. **`docker build` живёт в этом виртуальном Linux**. Образ есть только
   внутри job, после `runs-on: ubuntu-latest` всё исчезает.
3. **Чтобы образ пережил job — нужно его `push` в registry**. GHCR,
   ECR, Docker Hub, etc.
4. **`GITHUB_TOKEN`** — автоматический токен, выдаётся на каждый run,
   живёт 1 час. Через него можно `docker login ghcr.io`.
5. **`packages: write`** — отдельная permission, без неё `docker push`
   в GHCR упадёт с 403, даже если токен есть.

### 3.2. Минимальный publish-job (готовый шаблон для копирования)

```yaml
name: Publish API image

on:
  push:
    branches: [main]
    tags: ['v*.*.*']
    paths:
      - 'api/**'
      - '.github/workflows/api-publish.yml'
  workflow_dispatch:

concurrency:
  group: api-publish-${{ github.ref }}
  cancel-in-progress: false   # не отменять публикации

permissions:
  contents: read
  packages: write

jobs:
  build-and-push:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@<sha>
        with:
          submodules: recursive
          token: ${{ secrets.GH_PAT }}

      - uses: docker/setup-buildx-action@<sha>

      - uses: docker/login-action@<sha>
        with:
          registry: ghcr.io
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}

      - id: meta
        uses: docker/metadata-action@<sha>
        with:
          images: ghcr.io/${{ github.repository_owner }}/js-notebook-api
          tags: |
            type=ref,event=branch
            type=sha,prefix=sha-,format=short
            type=semver,pattern={{version}}
            type=semver,pattern={{major}}.{{minor}}
            type=raw,value=latest,enable={{is_default_branch}}

      - uses: docker/build-push-action@<sha>
        with:
          context: ./api
          push: true
          tags: ${{ steps.meta.outputs.tags }}
          labels: ${{ steps.meta.outputs.labels }}
          cache-from: type=gha,scope=api
          cache-to: type=gha,mode=max,scope=api
          provenance: true
          sbom: true
```

### 3.3. Пошагово, что вам сделать самому в первый раз

1. **Включить GHCR.** В организации `Settings → Packages` разрешить
   создание packages. По умолчанию включено.
2. **Permission на репо.** В `Settings → Actions → General → Workflow permissions`
   выбрать `Read and write permissions` (или явно прописать в workflow).
3. **Записать `permissions: packages: write` в workflow**.
4. **Залить workflow в `main`** (через PR, конечно).
5. **Открыть `Packages`** в правой колонке репозитория — там должен
   появиться `js-notebook-api` после первого успешного publish.
6. **Сделать package public/private** — по умолчанию private. Если хотите,
   чтобы любой мог `docker pull` без логина, сделайте public в настройках
   пакета.
7. **Локально проверить pull:**
   ```bash
   echo $GHCR_TOKEN | docker login ghcr.io -u <github-username> --password-stdin
   docker pull ghcr.io/<org>/js-notebook-api:main
   docker run --rm -p 8000:8000 ghcr.io/<org>/js-notebook-api:main
   curl http://localhost:8000/api/v1/health
   ```

### 3.4. Когда переключаться на AWS ECR

GHCR хорош для разработки, но при деплое в AWS ECS/EKS есть нюанс:

- pull из ghcr.io работает, но требует Docker registry secret в k8s/ECS;
- AWS ECR интегрирован с IAM, проще permission-модель;
- pull внутри AWS region — быстрее и бесплатнее по traffic.

Стратегия:
- На `main` пушите в **оба** registry (`ghcr.io` для удобства dev,
  `<account>.dkr.ecr.<region>.amazonaws.com` для AWS).
- Или сделайте ECR pull-through cache, который зеркалирует GHCR.

Это уже задача этапа E (AWS).

---

## 4. .gitignore в монорепо — что добавить

Submodules имеют свои собственные `.gitignore` (внутри `ui/.gitignore`,
`api/.gitignore`), и git **уважает их** при работе с submodule. Файлы вроде
`ui/node_modules/`, `api/.venv/` **не должны попадать** в индекс монорепо,
если submodule корректно настроен.

Проверить:

```bash
cd dmc-1-t2-notebook-mono
git status                # не должно показывать ui/dist, api/.venv и т.д.
git ls-files ui/dist      # должно быть пусто
git ls-files api/.venv    # должно быть пусто
```

**Если** статус чистый — добавлять в моно-`.gitignore` ничего не нужно.

**Если** что-то всё-таки попадает в индекс (например, на CI или при
неправильной настройке submodule) — добавьте перестраховку в корневой
`.gitignore`:

```gitignore
# Submodule build artifacts (защита от случайного коммита)
ui/dist/
ui/node_modules/
ui/coverage/
ui/.vite/
api/.venv/
api/__pycache__/
api/.pytest_cache/
api/.ruff_cache/
api/*.egg-info/
```

Это **не отменяет** игноры внутри submodule, а просто говорит:
«даже если submodule сошёл с ума и закоммитил это, монорепо его
сюда не пустит».

**Что в моно-`.gitignore` уже хорошо:** `.env`, `.env.*`, `node_modules/`,
`dist/`, `__pycache__/`, `.venv/`, `*.pem`, `*.key`, `*.crt`,
`api/.git`, `ui/.git` — всё правильно.

---

## 5. CODEOWNERS — для учебного проекта не нужен

Согласен с пользователем: если роли меняются раз в 2 недели, CODEOWNERS
становится головной болью. Можно вернуться к этому, когда команда
стабилизируется.

Альтернатива на сейчас: `.github/pull_request_template.md` с чек-листом
«кто проверил frontend / backend / infra» — это лёгкое решение и не
требует изменения настроек GitHub.

---

## 6. Чек-лист DevOps на ближайший месяц

- [ ] Стабилизировать docker compose локально.
- [ ] `concurrency` во все workflow.
- [ ] `cache-from: type=gha` во все Docker-билды.
- [ ] Поднять GHCR publish для api и ui (этап B).
- [ ] Добавить smoke-тест в docker-compose-ci.yml.
- [ ] Записать `scripts/setup-branch-protection.sh`.
- [ ] Заполнить реальные шаги в `ui/.github/workflows/pull-request.yml`.
- [ ] Изучить базовые AWS-сервисы (IAM, EC2, RDS, ECR, ECS).
- [ ] Прочитать <https://docs.docker.com/build/cache/backends/gha/>.
- [ ] Прочитать <https://docs.github.com/en/actions/security-guides/automatic-token-authentication>.
- [ ] Пройти лабу по GitHub Actions: <https://lab.github.com/githubtraining/github-actions>.

---

## 7. Где читать дальше

- GitHub Actions docs: <https://docs.github.com/actions>
- Docker build-push-action: <https://github.com/docker/build-push-action>
- Docker metadata-action: <https://github.com/docker/metadata-action>
- GHCR docs: <https://docs.github.com/packages/working-with-a-github-packages-registry/working-with-the-container-registry>
- AWS Well-Architected Framework: <https://aws.amazon.com/architecture/well-architected/>
- 12-Factor App: <https://12factor.net/> (основа для прод-ready приложений)
- Trivy: <https://aquasecurity.github.io/trivy/>
- cosign: <https://docs.sigstore.dev/cosign/overview/>
