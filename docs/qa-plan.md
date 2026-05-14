# QA Plan — JS Notebook SaaS

**Version:** 1.0  
**Date:** May 13, 2026  
**Owner:** TARDIS Team  

## 1. Overview

This document defines the quality assurance strategy for a SaaS web application that lets users write JavaScript code in a browser-based notebook, execute it client-side, and share notebooks with others.

**Tech Stack:** Python (backend), React/typescript (frontend)  
**Infrastructure:** AWS  
**API:** REST  
**Auth:** Email OTP → JWT  
**Scale:** Low-to-moderate traffic; highload is not a requirement

---

## 2. Test Objectives

- Verify core user flows work end-to-end: registration, login, code editing, execution, and sharing
- Ensure the OTP authentication flow is secure and reliable
- Validate REST API contracts are consistent and return correct status codes and payloads
- Catch regressions early through automated checks in CI
- Maintain code quality standards via lint and SonarQube gates

---

## 3. Scope

### In Scope

#### Main

| Area | Details |
|---|---|
| Authentication | OTP email delivery, OTP entry form, JWT issuance and expiry, token refresh |
| Notebook editor | Creating, editing, saving, and deleting notebooks |
| Code execution | Running JS in the browser sandbox, capturing stdout/errors |
| Sharing | Generating share links, viewing a shared notebook as guest |
| REST API | All public and authenticated endpoints |
| UI consistency | Cross-browser rendering, responsive layout |
| Code quality | Lint rules, SonarQube quality gate |

#### Frontend

- UI components
- Routing
- State management
- Forms & validation
- Accessibility
- Browser compatibility
- Responsive behavior

#### Backend (Python API)

- REST
- Authentication / authorization
- Database integrations
- Background jobs
- Error handling

#### Infrastructure (AWS)

- Deployment pipelines
- Logging / monitoring
- Backups

#### End-to-End SaaS Flows

- User registration
- Email verification
- Login / OTP → JWT
- CRUD workflows
- Notifications
- Admin operations

### Out of Scope

- Performance/load testing (highload is not a priority)
- Third-party vendor internal systems
- Mobile native apps
- Multi-language execution (only JS)
- Third-party email provider internals

---

## 4. Quality Objectives

| Objective | Target |
|---|---|
| Critical defect escape rate | 0 Sev-1 |
| API uptime | 99.9% |
| Avg page load | < 2.5 sec |
| Frontend bundle | < 7MB |
| Test automation coverage | > 70% core flows |
| Regression completion | < 4 hrs |
| Security vulnerabilities | 0 Critical / High |

---

## 5. Test Strategy

### 5.1 Static Analysis (shift-left, runs on every commit)

| Tool | What it checks | Fail condition |
|---|---|---|
| **TSLint** | React/JS code style and common errors | Any lint error, more than 10 warnings |
| **Flake8 / Ruff** | Python PEP 8, unused imports | Any lint error |
| **SonarQube** | Bugs, code smells, duplications, security hotspots, coverage | Quality Gate set to: coverage ≥ 70 %, 0 critical/blocker issues, duplications < 3 % |

SonarQube scan runs as part of the CI pipeline after the test suite and blocks the merge if the gate is not green.

### 5.2 Unit Tests

Fast tests for isolated logic.

- **Frontend (React):** Jest + React Testing Library for utility functions, hooks, and individual components (especially the editor and output panel). All methods and functions should be protected from using them with wrong typed argument values.
- **Backend (Python):** pytest for business logic — OTP generation/validation, JWT encoding, notebook CRUD, sharing logic
- Target coverage: **≥ 70 %** on both layers (enforced by SonarQube)

### 5.3 API Tests (REST)

- Tool: **pytest + httpx** (or a dedicated collection in a tool like Bruno)
- Contract tests asserting: HTTP status codes, response schema, required headers (e.g. `Content-Type`, `Authorization`)
- Run against a local or staging environment in CI
- AWS services mocks/stubs

### 5.4 End-to-End Tests (Playwright)

Full-stack browser tests covering the critical user journeys. Run in CI against a staging environment on every push to `main` or a release branch.

Real user workflows (details provided in section 6):

- Signup → OTP auth
- Working with notebooks - create, delete, update
- Execute JS code written in the notebook
- Share notebook to anonymous user

Configuration:
```
browsers: chromium, firefox, webkit
viewport: 1280x800 (desktop primary)
retries: 2 (CI), 0 (local)
workers: 4 (parallel)
reporter: HTML + JUnit XML (for CI artifacts)
```

### 5.5 Non-Functional Testing

- Performance (Load time, API response time, memory leaks)
- Security (SQL injection, XSS, Broken auth)
- Reliability
- Accessibility (not a priority, nice to have)
- Disaster recovery
- Logging (errors should be logged)

### 5.6 Manual Exploratory Testing (Regression test)

Performed by a QA engineer before each release on the staging environment. Focus areas:
- Edge cases in the code editor (large notebooks, Unicode, syntax errors, obscure symbols protection)
- OTP timing edge cases (expired code, resend throttle)
- Sharing link behavior (public vs authenticated)

---

## 5. Environments

| Environment | Purpose | Deployed by |
|---|---|---|
| **Local** | Developer self-testing | Developer |
| **CI** | Automated tests on every PR | GitHub Actions / AWS CodePipeline |
| **Staging** | Pre-release E2E, manual exploratory | CD on merge to `main` |
| **Production** | Live users | Manual promotion from staging |

All environments are hosted on AWS. Staging mirrors the production architecture (same instance types, same S3 buckets with separate namespaces, same email provider with sandbox mode).

---

## 6. Key Test Scenarios

### 6.1 Authentication

| # | Scenario | Expected result |
|---|---|---|
| A-01 | User enters a valid email and requests OTP | OTP email arrives within 60 s, form shows OTP input |
| A-02 | User submits the correct OTP before expiry | JWT returned, user redirected to dashboard |
| A-03 | User submits an incorrect OTP | Error message shown, attempt logged, OTP not consumed |
| A-04 | User submits an expired OTP (> 10 min) | Error: "Code expired", prompts resend |
| A-05 | User requests OTP again within the throttle window | Resend blocked, countdown shown |
| A-06 | User accesses a protected route without JWT | Redirected to login |
| A-07 | JWT expires mid-session | Session gracefully refreshes or re-prompts login |
| A-08 | OTP with a non-existent email | Behavior consistent (no user enumeration) |

### 6.2 Notebook Editor

| # | Scenario | Expected result |
|---|---|---|
| E-01 | User creates a new notebook | Empty editor shown, auto-saved with a default title |
| E-02 | User types JS code and runs it | Output/console panel shows correct result |
| E-03 | User runs code with a runtime error | Error displayed in output panel, app does not crash |
| E-04 | User saves a notebook manually | Success toast, notebook persisted on reload |
| E-05 | User renames a notebook | Title updated in sidebar and page title |
| E-06 | User deletes a notebook | Notebook removed, redirected to dashboard |
| E-07 | User has multiple notebooks | All listed in sidebar, switching works correctly |

### 6.3 Code Execution (sandboxed)

| # | Scenario | Expected result |
|---|---|---|
| X-01 | `console.log("hello")` | "hello" appears in output panel |
| X-02 | Infinite loop | Execution times out, user notified, page remains responsive |
| X-03 | `fetch()` to an external URL | Executes or is blocked per sandbox policy — behavior documented |
| X-04 | Syntax error in code | Parse error shown before execution attempt |

### 6.4 Sharing

| # | Scenario | Expected result |
|---|---|---|
| S-01 | Owner generates a share link | Unique URL produced, copyable |
| S-02 | Guest opens share link | Read-only view of the notebook, cannot edit |
| S-03 | Guest runs code in shared notebook | Execution works in guest mode |
| S-04 | Owner revokes share link | Link no longer accessible (404 or "not found") |
| S-05 | Share link for a deleted notebook | Returns 404 |

### 6.5 REST API

| # | Endpoint | Scenario | Expected status |
|---|---|---|---|
| R-01 | `POST /auth/request-otp` | Valid email | 200 |
| R-02 | `POST /auth/request-otp` | Malformed email | 422 |
| R-03 | `POST /auth/verify-otp` | Correct OTP | 200 + JWT |
| R-04 | `POST /auth/verify-otp` | Wrong OTP | 401 |
| R-05 | `GET /notebooks` | Authenticated | 200 + list |
| R-06 | `GET /notebooks` | No JWT | 401 |
| R-07 | `POST /notebooks` | Valid payload | 201 |
| R-08 | `DELETE /notebooks/:id` | Other user's notebook | 403 |
| R-09 | `GET /notebooks/:id/share` | Public share link | 200 (no auth) |

---

## 7. Entry and Exit Criteria

### Entry Criteria (before a test cycle begins)

- Build is deployed to the target environment without errors
- Smoke test (A-01, E-01, S-01) passes manually
- Test data (seed users, sample notebooks) is loaded
- All blocking bugs from the previous cycle are resolved

### Exit Criteria (before releasing to production)

- All Playwright E2E scenarios pass on staging
- SonarQube Quality Gate is green
- No open `Critical` or `Blocker` defects
- Manual exploratory session completed with no new Critical findings
- Test results and coverage report attached to the release ticket
- PO approval
- Rollback plan

---

## 8. Defect Management

| Severity | Definition | Resolution SLA |
|---|---|---|
| **Blocker** | Prevents core flow (login, run code, share) | Must fix before release |
| **Critical** | Major feature broken, no workaround | Fix within current sprint |
| **Major** | Feature degraded, workaround exists | Fix in next sprint |
| **Minor** | Cosmetic, UX polish | Backlog |

Defects are filed in the project issue tracker with: steps to reproduce, environment, screenshots/logs, and severity label.

---

## 9. CI/CD Quality Gates

Every pull request must pass the following before merge:

```
1. Lint (ESLint + Ruff) — no errors
2. Unit tests — all pass, coverage ≥ 70 %
3. API tests — all pass
4. SonarQube scan — Quality Gate green
5. Playwright E2E (smoke subset) — all pass
```

Full E2E suite runs nightly against staging and on merge to `main`.

---

## 10. Risks and Mitigations

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| OTP email delayed by provider | Medium | High | Set OTP TTL to 10 min; test with sandbox; monitor delivery latency |
| JS sandbox escape | Low | High | Use `iframe` sandbox with strict CSP; include security review before release |
| JWT secret misconfigured in AWS | Low | High | Infrastructure-as-code with automated secret rotation check in CI |
| Flaky Playwright tests blocking CI | Medium | Medium | Retry policy (2 retries), quarantine tag for known-flaky tests |
| SonarQube coverage drop after fast feature work | Medium | Medium | PR-level coverage diff check; block merge if coverage drops > 5 % |

---

## 11. Roles and Responsibilities

| Role | Responsibility |
|---|---|
| Developer | Unit tests, fixing lint/SonarQube issues, reviewing test failures, smoke testing |
| QA Engineer | E2E test authoring (Playwright), manual exploratory testing, defect triage |
| Tech Lead | Quality Gate thresholds, release go/no-go decision |
| DevOps | CI pipeline, staging environment, AWS secret management |
