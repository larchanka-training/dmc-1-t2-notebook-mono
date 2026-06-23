# QA Info — Release Certification Report (JS Notebook)

**Issue:** [#157 — S3 QA: Release Certification](https://github.com/larchanka-training/js-notebook/issues/157)
**Team:** T2 · **Prepared by:** QA · **Date:** 2026-06-20
**Decision:** ✅ **Go** (see [§7](#7-go--no-go-decision))

---

## 1. Build under test

| Component | Ref | Version |
|---|---|---|
| Monorepo | `qa/issue-157-release-certification` @ `0a683aa` (off `main`) | — |
| `api` submodule | `8439b84` | `v0.1.1-98-g8439b84` |
| `ui` submodule | `0082a09` | `v1.0.0-391-g0082a09` |
| Environment | Local stack (`docker compose`) + Liquibase `dev` migrations | API `0.2.0` |

> Target environment for this cycle is the **local stack** (`./start-services.sh`),
> per the agreed scope. There is no staging environment yet (`docs/qa/qa-plan.md` §5);
> the cloud `production` and per-PR previews are out of scope for this certification.

---

## 2. Scope of the regression cycle

A full functional regression across the implemented product surface, driven by a
new standalone automation project: [`autotests/`](../../autotests/) — Playwright
**E2E** + pytest **API**, one merged **Allure** report. Traceability to the
`AT-*` roadmap (`docs/qa/autotest-tasks.md`) and the `TC-*` manual cases (`qa/`) is
in [`autotests/TRACEABILITY.md`](../../autotests/TRACEABILITY.md).

Areas covered: **authentication (OTP/JWT)**, **notebooks CRUD + sync**,
**AI-context persistence**, **LLM contract/validation**, **code execution
(QuickJS/WASM)**. Areas **not** covered because the feature does not exist —
see [§6 Known limitations](#6-known-limitations).

---

## 3. Test execution summary

### 3.1 API suite (pytest, black-box over HTTP) — ✅ EXECUTED

Ran against the live local stack (`http://localhost:8000/api/v1`), migrations
applied via Liquibase. **Result: 34/34 passed**, stable across 5 consecutive
runs.

| Module | Tests | Result |
|---|---|---|
| `test_health.py` | 3 | ✅ |
| `test_auth.py` | 9 | ✅ |
| `test_notebooks.py` | 13 | ✅ |
| `test_ai_context.py` | 4 | ✅ |
| `test_llm.py` | 5 | ✅ (contract/validation only — no Bedrock) |
| **Total** | **34** | **✅ 34 passed** |

Smoke subset (`-m smoke`): **9/9 passed**.

### 3.2 E2E suite (Playwright) — ✅ EXECUTED

Run end-to-end via the **containerized runner**
(`autotests/scripts/run-containerized.sh regression`): the stack is brought up in
containers, migrations applied, and the browser drives the real UI at
`http://notebook.com` (a same-origin proxy → Vite + FastAPI). **Result: 12/12
passed.** Selectors were authored against the **actual** `ui@0082a09` source
(ARIA roles/labels, `data-cell-id` / `data-state` / `data-output-segment`), then
corrected against the live DOM.

| AT | Spec | Priority | Status |
|---|---|---|---|
| AT-AUTH-01 | `auth/otp-login.spec.ts` | smoke | ✅ |
| AT-AUTH-02/04/05 | `auth/*.spec.ts` | regression | ✅ |
| AT-NB-01 | `notebook/create.spec.ts` | smoke | ✅ |
| AT-NB-02/04/05 | `notebook/{rename,delete,multi-notebook-nav}.spec.ts` | regression | ✅ |
| AT-NB-03 | `notebook/save-persist.spec.ts` | regression | ✅ (UI edit → background autosync → verified server-side) |
| AT-EX-01 | `execution/console-log.spec.ts` | smoke | ✅ |
| AT-EX-02/03 | `execution/*.spec.ts` | regression | ✅ |

The dev stack is single-instance, so E2E runs with limited parallelism
(`PW_WORKERS=2`) and retries (`PW_RETRIES=2`) to absorb transient load flakiness.

---

## 4. Critical bugs

**None.** No Blocker or Critical defect was found in the executed (API) surface.
Core flows — passwordless OTP login, JWT issue/refresh/rotation/reuse-detection,
notebooks CRUD with owner isolation, AI-context persistence, LLM input
validation — all behave per contract.

---

## 5. Observations (non-blocking)

| ID | Severity | Finding | Notes |
|---|---|---|---|
| OBS-1 | Low | **Not read-your-writes consistent at machine speed.** `get_db` commits in the dependency teardown (`yield; commit`, `api/app/core/db.py`), which races sending the response. A follow-up request issued microseconds later (OTP verify right after request; GET right after DELETE) can miss the write. | **Real users are unaffected** — a human takes seconds between steps. Surfaced only by back-to-back automated calls. Mitigated in the harness by a uniform **1s settle after every mutating request** (temporary shield). Filed as a backend bug — `larchanka-training/js-notebook#166` (commit-before-response). Not a release blocker. |
| OBS-2 | Info | **Cross-user GET returns `403`, not `404`.** A known-id notebook owned by another user yields `403 Forbidden` (truly-absent ids yield `404`). | Correct & safe (owner-scoped). Documented so the contract expectation is explicit; minor existence-disclosure trade-off vs. `404`. |

---

## 6. Known limitations

These bound the certification — they are **product scope**, not test gaps:

1. **Sharing is not implemented** (UI *or* API). No generate-link/revoke UI
   (the sidebar "Duplicate" is disabled), no backend share routes (notebooks are
   strictly owner-scoped). → `AT-SH-*`, `qa/*/sharing` cases are **not
   automatable**; kept as documented skips.
2. **LLM generation runs in-browser (WebLLM)**, not through the backend proxy.
   The roadmap's fallback-chain E2E (`AT-LLM-02/03/04`) and `mockWasmLlm` happy
   path don't match reality; real browser inference needs a multi-hundred-MB
   model download. The backend `/llm/generate` **exists** and is covered at the
   contract level (auth, prompt validation, edit-mode rule); **real generation
   needs Amazon Bedrock credentials** (out of local scope).
3. **No `data-testid` in the UI** — E2E relies on ARIA roles/labels and existing
   `data-*` hooks. Robust today, but a deliberate `data-testid` pass would harden
   the smoke suite.
4. **No staging environment** (`docs/qa/qa-plan.md` §5) — this cycle certifies the
   **local** build only.
5. **Host tooling** — E2E/API/Allure need Node + browsers + Python + Java. The
   containerized runner packs all of these into Docker, so the host needs only
   Docker (see §3.2 / `autotests/README.md`).

---

## 7. Go / No-Go decision

### ✅ Go

**Rationale.** Both regressions are **green** on the target build, executed
against a real containerized stack — **API 34/34** and **E2E 12/12**. **No
Blocker/Critical defects**; the two observations are non-blocking and do not
affect real users.

**Gate status:**

- [x] API regression green on the target build (34/34)
- [x] E2E smoke green (`AT-AUTH-01`, `AT-NB-01`, `AT-EX-01`)
- [x] E2E regression green (auth/notebook/execution — 12/12)
- [x] Known limitations documented and accepted by the team
- [x] No open Blocker/Critical defects

**Scope caveat.** This is a **Go for the implemented surface**. Sharing and the
LLM backend-proxy path are **not implemented** — they are out of scope for this
release and a **No-Go for those features** until built (see §6).

---

## 8. How to reproduce

### Fastest — one command, host needs only Docker

```bash
autotests/scripts/run-containerized.sh regression   # smoke | regression | all
```

Brings the stack up in containers, applies migrations, runs both suites (Node +
Playwright browsers + Python + Allure all baked into the runner image), writes
the merged report to `autotests/allure-report`, and tears down. This is the
mandatory pre-PR gate (`AGENTS.md` §11, `docs/qa/qa-plan.md` §9.1).

### Manual / host-driven

```bash
# 1. Bring up the local stack
cp api/.env.example api/.env && cp ui/.env.example ui/.env
docker compose up -d --build

# 2. Apply DB migrations (the app does not migrate on boot)
docker build -t jsnotes-liquibase:local api/liquibase
docker run --rm --network "$(basename "$PWD")_default" \
  -e LIQUIBASE_COMMAND_URL=jdbc:postgresql://postgres:5432/wiki \
  -e LIQUIBASE_COMMAND_USERNAME=admin -e LIQUIBASE_COMMAND_PASSWORD=admin123 \
  -e LIQUIBASE_COMMAND_CHANGELOG_FILE=changelog-master.xml \
  -e LIQUIBASE_COMMAND_CONTEXTS=dev jsnotes-liquibase:local update

# 3. API suite (executed for this report)
cd autotests/api && python -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
API_BASE_URL=http://localhost:8000/api/v1 python -m pytest --alluredir ../allure-results/api

# 4. E2E suite (needs Node + browsers)
cd ../e2e && npm install && npx playwright install --with-deps chromium
BASE_URL=http://notebook.com API_BASE_URL=http://localhost:8000/api/v1 npx playwright test

# 5. Merged Allure report (needs Java + Allure CLI)
allure generate ../allure-results/api ../allure-results/e2e --clean -o ../allure-report
allure open ../allure-report
```

See [`autotests/README.md`](../../autotests/README.md) for full instructions.
