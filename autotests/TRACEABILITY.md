# Traceability — autotests ↔ roadmap ↔ manual cases

Maps each automated test to the `docs/qa/autotest-tasks.md` roadmap ID (`AT-*`),
the `qa/` manual cases (`TC-*`) and `docs/qa/qa-plan.md` scenarios, with the
**implementation status against the live code** (api@8439b84 / ui@0082a09).

Legend: ✅ automated & **verified green** against the live containerized stack ·
⏭️ skipped (documented limitation — feature not implemented).

> Status verified by `autotests/scripts/run-containerized.sh regression`
> (api@8439b84 / ui@0082a09): **API 34/34 passed**, **E2E 12/12 passed**.

## E2E (Playwright) — `autotests/e2e/`

| AT | Priority | Spec | Scenario | Status |
|---|---|---|---|---|
| AT-INFRA-01 | infra | `fixtures/index.ts` | — | ✅ |
| AT-INFRA-02 | infra | `pages/*.page.ts` | — | ✅ |
| AT-AUTH-01 | smoke | `auth/otp-login.spec.ts` | A-01/A-02 | ✅ |
| AT-AUTH-02 | regression | `auth/otp-invalid.spec.ts` | A-03 | ✅ |
| AT-AUTH-04 | regression | `auth/otp-resend-throttle.spec.ts` | A-05 | ✅ |
| AT-AUTH-05 | regression | `auth/unauthenticated-redirect.spec.ts` | A-06 | ✅ (route is `/`, not `/dashboard`) |
| AT-AUTH-03 | regression | — | A-04 | ⏭️ needs API mock of expiry; deferred |
| AT-AUTH-06/07 | edge | — | A-07/A-08 | ⏭️ edge, out of smoke+regression scope |
| AT-NB-01 | smoke | `notebook/create.spec.ts` | E-01 | ✅ |
| AT-NB-02 | regression | `notebook/rename.spec.ts` | E-05 | ✅ (in-session rename; cross-reload persistence is the API suite's job) |
| AT-NB-03 | regression | `notebook/save-persist.spec.ts` | E-04 | ✅ (UI edit → background autosync → verified server-side via API) |
| AT-NB-04 | regression | `notebook/delete.spec.ts` | E-06 | ✅ |
| AT-NB-05 | regression | `notebook/multi-notebook-nav.spec.ts` | E-07 | ✅ |
| AT-EX-01 | smoke | `execution/console-log.spec.ts` | X-01 | ✅ |
| AT-EX-02 | regression | `execution/syntax-error.spec.ts` | X-04 | ✅ |
| AT-EX-03 | regression | `execution/infinite-loop-timeout.spec.ts` | X-02 | ✅ (30s deadline → `halted`) |
| AT-EX-04 | edge | — | X-03 | ⏭️ edge |
| AT-SH-01..04 | smoke/reg/edge | `sharing/sharing.spec.ts` | S-01..05 | ⏭️ **sharing not implemented** |
| AT-LLM-01..04 | smoke/reg | `llm/llm-generation.spec.ts` | L-01..04 | ⏭️ **UI uses in-browser WebLLM** |
| AT-LLM-05..07 | reg/edge | — | L-05/06/09/10 | ⏭️ see API validation tests |

Notes on the real UI (discovered while wiring these): `/` opens a 19-cell demo
notebook; backend notebooks render as sidebar `<button>`s (title text), the
local floor notebook as `<a href="/">`; session is persisted as a Reatom
`withLocalStorage` envelope (`{data,id,timestamp,to,version}`), which the
`authedPage` fixture mirrors.

## API (pytest) — `autotests/api/tests/`

| Area | Tests | TC / scenario | Status |
|---|---|---|---|
| Health | `test_health.py` (3) | TC-INFRA-*, R-00 | ✅ |
| Auth | `test_auth.py` (9) | TC-API-AUTH-01..10, A-* | ✅ |
| Notebooks | `test_notebooks.py` (13) | TC-API-NB-01..12, E-* | ✅ |
| AI context | `test_ai_context.py` (4) | TC-API-*, context-ai-workflow | ✅ |
| LLM | `test_llm.py` (5) | TC-API-LLM-*, L-05/06 | ✅ contract only (no Bedrock) |
| Sharing | — | qa/api sharing | ⏭️ no endpoints exist |
