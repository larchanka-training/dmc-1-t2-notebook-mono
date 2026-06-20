# JS Notebook — Autotests (E2E + API) with Allure

A standalone test-automation project for the JS Notebook SaaS, created for
issue **#157 (S3 QA — Release Certification)**. It runs the regression cycle
that backs the Go/No-Go decision in [`../docs/qa/qa-info.md`](../docs/qa/qa-info.md).

Two suites, **one merged [Allure](https://allurereport.org/) report**:

| Suite | Tech | Folder | What it covers |
|---|---|---|---|
| **E2E** | Playwright + `allure-playwright` (TypeScript) | [`e2e/`](e2e/) | Real browser flows: OTP login, notebook CRUD, code execution |
| **API** | pytest + `allure-pytest` (httpx, black-box) | [`api/`](api/) | `/api/v1` contract: health, auth, notebooks, ai-context, llm validation |

It is intentionally **separate** from the in-repo unit/integration tests
(`ui/` Vitest, `api/` pytest TestClient): those mock at a boundary, this drives
a **running stack** end-to-end, the way a release-certification regression does.

Traceability to the roadmap (`docs/qa/autotest-tasks.md`, `AT-*`) and the manual
test cases (`qa/`, `TC-*`) is in [`TRACEABILITY.md`](TRACEABILITY.md).

---

## Prerequisites

- The **local stack running** (from the monorepo root):
  ```bash
  ./start-services.sh          # api :8000, ui :5173, proxy :80 (notebook.com)
  ```
  The backend must be **local-like** (`APP_ENV` ∈ `dev`/`local`/`test`) so that
  `POST /auth/otp/request` returns the dev OTP in its body — that is how both
  suites log in without an email inbox.
- **Node ≥ 18** + **pnpm or npm** (for the E2E suite).
- **Python ≥ 3.12** (for the API suite).
- **Allure CLI** for the HTML report — needs **Java**.
  See https://allurereport.org/docs/install/ . Without it you still get raw
  results under `allure-results/`.

> `/etc/hosts` must map `notebook.com` / `api.notebook.com` to `127.0.0.1`
> (see the root `README.md`) for the proxy `BASE_URL`. Or point `BASE_URL` at
> `http://localhost:5173` to bypass the proxy.

---

## Install

```bash
# E2E
cd autotests/e2e
npm install            # or: pnpm install
npx playwright install --with-deps chromium

# API
cd ../api
python -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
```

---

## Run

### Containerized — one command, host needs only Docker (recommended, pre-PR gate)

Brings the whole stack up in containers, applies migrations, runs **both suites**
inside a runner image (Node + Playwright browsers + Python + Allure all baked
in), writes the merged report to `autotests/allure-report`, then tears down.
Exit code mirrors the result, so it gates a pre-PR check (`AGENTS.md` §11):

```bash
autotests/scripts/run-containerized.sh regression   # or: smoke | all
```

No `pnpm`/`npm`/Python/Java needed on the host — that solves the local-tooling
gap. Knobs: `PW_WORKERS` (default 2), `PW_RETRIES` (default 2), `SUITE`.

### Host-driven — both suites against an already-running stack → one Allure report

```bash
# from the monorepo root, with the stack up + migrations applied:
API_BASE_URL=http://localhost:8000/api/v1 BASE_URL=http://notebook.com \
  autotests/scripts/run-all.sh all        # or: smoke | regression
```

### Just one suite

```bash
# API
cd autotests/api && . .venv/bin/activate
python -m pytest -m smoke --alluredir ../allure-results/api

# E2E
cd autotests/e2e
BASE_URL=http://notebook.com API_BASE_URL=http://localhost:8000/api/v1 \
  npx playwright test --grep @smoke
```

### View the report

```bash
allure generate autotests/allure-results/api autotests/allure-results/e2e --clean -o autotests/allure-report
allure open autotests/allure-report
```

---

## Test selection

- **Smoke** (PR-blocking): Playwright `--grep @smoke`; pytest `-m smoke`.
  E2E: `AT-AUTH-01`, `AT-NB-01`, `AT-EX-01`. API: health, OTP request/verify,
  `/auth/me` guard, notebooks create/get/list-auth, llm auth.
- **Regression** (nightly): add `@regression` / `-m "smoke or regression"`.

## Configuration

| Env var | Default | Used by |
|---|---|---|
| `BASE_URL` | `http://notebook.com` | E2E (browser origin) |
| `API_BASE_URL` | `http://localhost:8000/api/v1` | both (login + seeding) |
| `API_TIMEOUT` | `15` | API suite httpx timeout (s) |

## Known limitations (see qa-info)

- **Sharing is not implemented** (UI or API) → `AT-SH-*` kept as skipped
  placeholders; `qa/*/sharing` cases are not automatable.
- **LLM generation runs in-browser (WebLLM)**, not via the backend proxy →
  `AT-LLM-*` E2E kept skipped; the backend `/llm/generate` is covered at the
  contract/validation level only (real generation needs Bedrock creds).
- **No `data-testid`** in the UI — selectors use ARIA roles/labels and the
  existing `data-cell-id` / `data-state` / `data-output-segment` hooks.
