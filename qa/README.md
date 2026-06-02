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
| **Blocker** | Blocks a core scenario (login, code execution, sharing) |
| **Critical** | Core feature broken, no workaround |
| **Major** | Feature degraded, workaround exists |
| **Minor** | Cosmetic, UX polish |
