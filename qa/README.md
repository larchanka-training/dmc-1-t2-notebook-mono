# QA Test Cases — JS Notebook SaaS

**Project:** JS Notebook  
**Version:** 1.0  
**Owner:** TARDIS Team

---

## Folder Structure

| Folder | Scope |
|---|---|
| `ui/` | Frontend component and interaction test cases |
| `api/` | REST API contract and integration test cases |
| `e2e/` | End-to-end user scenario test cases |
| `security/` | Auth, access control, and security test cases |
| `infrastructure/` | Docker, CI/CD, and deployment test cases |

## Priority Levels

| Priority | Meaning |
|---|---|
| **Smoke** | Blocks CI on every PR — must always pass |
| **Regression** | Nightly run and merge to `main` |
| **Edge** | Nightly run, separate schedule acceptable |

## Test Case Status

| Status | Meaning |
|---|---|
| ✅ Pass | Test passed |
| ❌ Fail | Test failed — file a bug |
| ⏭ Skip | Skipped — environment not available |
| 🔄 In Progress | Currently being executed |

## Bug Severity

| Severity | Definition |
|---|---|
| **Blocker** | Blocks a core scenario (login, code execution) |
| **Critical** | Core feature broken, no workaround |
| **Major** | Feature degraded, workaround exists |
| **Minor** | Cosmetic, UX polish |

## Automation & implementation status

These manual cases are automated (where the feature exists) by the standalone
project [`../autotests/`](../autotests/) — Playwright E2E + pytest API, one
Allure report. Traceability: [`../autotests/TRACEABILITY.md`](../autotests/TRACEABILITY.md).
The release-certification run (issue #157) is [`../docs/qa/qa-info.md`](../docs/qa/qa-info.md).

**Not currently automatable (feature not implemented — code is source of truth):**

- **Sharing** (`ui/sharing.md`, the sharing steps in `e2e/user-scenarios.md`):
  there is no sharing UI and no backend share endpoints. Treat these as pending
  the feature, not as failing tests.
- **LLM via backend proxy** (`ui/llm-generation.md`, `api/llm.md` generation):
  the UI generates code in-browser (WebLLM); the backend `/llm/generate` is
  covered only at the contract/validation level (real generation needs Bedrock).
