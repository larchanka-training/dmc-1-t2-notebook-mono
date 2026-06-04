# QA Plan — JS Notebook SaaS

**Version:** 1.0  
**Date:** May 13, 2026  
**Owner:** TARDIS Team  

---

## 1. Overview

This document defines the quality assurance strategy for the SaaS web application that allows users to write JavaScript code in a browser-based notebook, execute it on the client side, and share notebooks with other users.

**Technology stack:** Python 3.12 (backend), React/TypeScript (frontend)  
**Code generation:** LLM in the browser (WASM) → LLM on the backend → OpenAI API (fallback chain)  
**Infrastructure:** AWS  
**API:** REST  
**Authentication:** Email OTP → JWT  
**Load:** Low and moderate; high loads are not a priority

---

## 2. Testing Goals

- Verify that core user scenarios work end to end: registration, login, code editing, execution, and sharing
- Ensure that the OTP-based authentication flow is secure and reliable
- Confirm that REST API contracts are consistent and return correct status codes and response bodies
- Detect regressions early through automated checks in CI
- Maintain code quality standards using lint and SonarQube

---

## 3. Coverage Scope

### In Scope

#### Core

| Area | Details |
|---|---|
| Authentication | OTP delivery via email, OTP input form, JWT issuance and expiration, token refresh |
| Notebook editor | Creating, editing, saving, and deleting notebooks |
| Code execution | Running JS in the browser sandbox, capturing stdout/errors |
| Sharing | Generating share links, guest viewing of a notebook |
| LLM code generation | Prompt input field, WASM LLM invocation, fallback to backend LLM, fallback to OpenAI API, inserting the result into the editor |
| REST API | All public and authenticated endpoints |
| UI consistency | Rendering across different browsers, responsive layout |
| Code quality | Lint rules, SonarQube quality gate |

#### Frontend

- UI components
- Routing
- State management
- Forms and validation
- Accessibility
- Browser compatibility
- Responsive behavior
- Loading and inference of the WASM LLM in the browser
- Generation state UI (loading, streaming, error)

#### Backend (Python 3.12 API)

- REST
- Authentication / authorization
- Database integration
- Background jobs
- Error handling
- Proxy endpoint for the backend LLM
- Integration with the OpenAI API and fallback-chain management

#### Infrastructure (AWS)

- Deployment pipelines
- Logging / monitoring
- Backups

#### End-to-end SaaS Scenarios

- User registration
- Email verification
- Login / OTP → JWT
- CRUD operations
- Notifications
- Administrative operations
- Code generation via LLM (all three tiers: WASM → backend → OpenAI)

### Out of Scope

- Load testing (high loads are not a priority)
- Internal systems of third-party providers
- Native mobile applications
- Multi-language code execution (JS only)
- Internal components of the third-party email provider

---

## 4. Quality Metrics

| Metric | Target value |
|---|---|
| Critical defect escape rate | 0 Sev-1 |
| API availability | 99.9% |
| Average page load time | < 2.5 sec |
| Frontend bundle size | < 7 MB |
| Automation coverage | > 70% of key scenarios |
| Regression cycle time | < 4 h |
| Security vulnerabilities | 0 critical / high |

---

## 5. Testing Strategy

### 5.1 Static Analysis (shift-left, runs on every commit)

| Tool | What it checks | Failure condition |
|---|---|---|
| **ESLint** | Style and common errors in TypeScript/JS code (frontend) | Any lint error, more than 10 warnings |
| **Ruff** | PEP 8, unused imports, Python 3.12 code style (backend) | Any lint error |
| **SonarQube** | Bugs, code smells, duplicates, security hotspots, coverage | Quality Gate: coverage ≥ 70%, 0 critical/blocker issues, duplication < 3% |

The SonarQube scan runs in the CI pipeline after the test run and blocks the merge if the quality gate is not passed.

### 5.2 Unit Tests

Fast tests for isolated logic.

- **Frontend (React):** Vitest + Testing Library — utility functions, hooks, and individual components (especially the editor and the output panel). All methods and functions must be guarded against being called with arguments of the wrong type.
- **Backend (Python 3.12):** pytest — business logic: OTP generation and validation, JWT encoding, notebook CRUD, sharing logic, LLM fallback-chain logic (WASM → backend → OpenAI)
- Target coverage: **≥ 70%** at both layers (enforced by SonarQube)

### 5.3 API Tests (REST)

- Tool: **pytest + httpx** (or a collection in a tool such as Bruno)
- Contract tests: HTTP statuses, response schema, required headers (`Content-Type`, `Authorization`)
- Run against a local or staging environment in CI
- Mocks/stubs for AWS services

### 5.4 End-to-End Tests (Playwright)

Full-stack browser tests covering key user scenarios. Run in CI against staging on every push to `main` or a release branch.

Real user scenarios (details in section 6):

- Registration → OTP authentication
- Working with notebooks — creation, deletion, updates
- Executing JS code written in a notebook
- Sharing a notebook with an anonymous user
- Code generation via LLM (happy path through WASM + smoke fallback to backend and OpenAI)

Configuration:
```
browsers: chromium, firefox, webkit
viewport: 1280x800 (desktop, primary)
retries: 2 (CI), 0 (local)
workers: 4 (parallel)
reporter: HTML + JUnit XML (CI artifacts)
```

### 5.5 Non-Functional Testing

- Performance (load time, API response time, memory leaks, WASM LLM initialization time)
- Security (SQL injection, XSS, broken authentication)
- Reliability
- Accessibility (not a priority, nice to have)
- Failure recovery
- Logging (errors must be logged)

### 5.6 Manual Exploratory Testing (regression)

Performed by a QA engineer before each release in the staging environment. Focus areas:
- Edge cases in the code editor (large notebooks, Unicode, syntax errors, protection against non-standard characters)
- OTP timing edge cases (expired code, resend rate limiting)
- Share-link behavior (public vs. authenticated access)

---

## 5. Environments

| Environment | Purpose | Deployed by |
|---|---|---|
| **Local** | Developer self-check | Developer |
| **CI** | Automated tests on every PR | GitHub Actions / AWS CodePipeline |
| **Staging** | Pre-release E2E, manual exploration | CD on merge to `main` |
| **Production** | Live users | Manual promotion from staging |

All environments are hosted on AWS. Staging mirrors the production architecture (same instance types, same S3 buckets with separate namespaces, same email provider in sandbox mode).

> **Note (2026-05-23):** this is the **target** environment model. Right now
> only `production` actually exists (staging is **not yet deployed**), and the
> "dev" role is played by the preview-per-PR environments (see
> `preview-dev-environments-v2.md`). At this stage CD deploys to `production`
> via GitHub Actions (`deploy.md`).

---

## 6. Key Test Scenarios

### 6.1 Authentication

| # | Scenario | Expected result |
|---|---|---|
| A-01 | User enters a valid email and requests an OTP | The OTP email arrives within 60 sec, the form shows the OTP input field |
| A-02 | User enters the correct OTP before it expires | A JWT is returned, the user is redirected to the dashboard |
| A-03 | User enters an incorrect OTP | An error message is shown, the attempt is logged, the OTP is not consumed |
| A-04 | User enters an expired OTP (> 10 min) | Error: "Code expired," a resend is offered |
| A-05 | User requests an OTP again during the rate-limit period | Resend is blocked, a countdown is shown |
| A-06 | User navigates to a protected route without a JWT | Redirect to the login page |
| A-07 | JWT expires mid-session | The session refreshes gracefully or a re-login is requested |
| A-08 | OTP for a non-existent email | Behavior is consistent (no user enumeration) |

### 6.2 Notebook Editor

| # | Scenario | Expected result |
|---|---|---|
| E-01 | User creates a new notebook | An empty editor is shown, autosave with a default title |
| E-02 | User writes JS code and runs it | The output panel shows the correct result |
| E-03 | User runs code with a runtime error | The error is displayed in the output panel, the app does not crash |
| E-04 | User saves the notebook manually | Success toast, the notebook persists after reload |
| E-05 | User renames the notebook | The title updates in the sidebar and on the browser tab |
| E-06 | User deletes the notebook | The notebook is deleted, redirect to the dashboard |
| E-07 | User has multiple notebooks | All are shown in the sidebar, switching works correctly |

### 6.3 Code Execution (sandbox)

| # | Scenario | Expected result |
|---|---|---|
| X-01 | `console.log("hello")` | "hello" appears in the output panel |
| X-02 | Infinite loop | Execution is interrupted by timeout, the user is notified, the page stays responsive |
| X-03 | `fetch()` to an external URL | Executes or is blocked according to the sandbox policy — behavior is documented |
| X-04 | Syntax error in the code | The parsing error is shown before execution is attempted |

### 6.4 Sharing

| # | Scenario | Expected result |
|---|---|---|
| S-01 | Owner generates a share link | A unique URL is created, available to copy |
| S-02 | Guest opens the share link | The notebook is displayed in read-only mode, editing is disabled |
| S-03 | Guest runs code in a shared notebook | Execution works in guest mode |
| S-04 | Owner revokes the share link | The link is no longer accessible (404 or "not found") |
| S-05 | Share link for a deleted notebook | Returns 404 |

### 6.5 REST API

| # | Endpoint | Scenario | Expected status |
|---|---|---|---|
| R-01 | `POST /auth/request-otp` | Valid email | 200 |
| R-02 | `POST /auth/request-otp` | Invalid email format | 422 |
| R-03 | `POST /auth/verify-otp` | Correct OTP | 200 + JWT |
| R-04 | `POST /auth/verify-otp` | Incorrect OTP | 401 |
| R-05 | `GET /notebooks` | Authenticated request | 200 + list |
| R-06 | `GET /notebooks` | Without a JWT | 401 |
| R-07 | `POST /notebooks` | Valid payload | 201 |
| R-08 | `DELETE /notebooks/:id` | Another user's notebook | 403 |
| R-09 | `GET /notebooks/:id/share` | Public share link | 200 (without authorization) |
| R-10 | `POST /llm/generate` | Valid prompt, backend LLM succeeded | 200 + generated code |
| R-11 | `POST /llm/generate` | Backend LLM failed, fallback to OpenAI | 200 + code, header `X-LLM-Source: openai` |
| R-12 | `POST /llm/generate` | Empty prompt | 422 |
| R-13 | `POST /llm/generate` | Without a JWT | 401 |
| R-14 | `POST /llm/generate` | OpenAI unavailable (all tiers exhausted) | 503 + error message |

### 6.6 LLM Code Generation

| # | Scenario | Expected result |
|---|---|---|
| L-01 | User enters a prompt, the WASM LLM succeeds | Code is inserted into the editor, no network request is sent |
| L-02 | The WASM LLM cannot process the request → fallback to the backend LLM | The backend LLM returns code; the user does not notice the switch |
| L-03 | The backend (Cloud agent) fails | Clear error to the user, editor not modified — there is no third-provider fallback in the MVP (see `ai-architecture.md` §6.2) |
| L-04 | Both tiers unavailable (T1 cannot start **and** T2 is down) | A clear error message is shown, the editor is not modified |
| L-05 | Empty prompt field | The "Generate" button is disabled or an inline validation error is shown |
| L-06 | Prompt longer than the allowed character limit | A character counter with an error is shown, the request is not sent |
| L-07 | Generated code is inserted into the editor | Inserted as a **separate new code cell below the Prompt Cell**, in a `proposal` state awaiting accept/reject (`ai-architecture.md` §4.4) |
| L-08 | Generation is in progress — the user closes the tab | The incomplete result is not saved, the state resets correctly |
| L-09 | The WASM LLM is not yet loaded (first request) | A loading indicator is shown, the request is queued until the model is ready |
| L-10 | The browser does not support **WebGPU** (WebLLM cannot start) | The *In-browser agent* button is disabled with a tooltip; the user reaches for *Cloud agent* (capability gate, `ai-architecture.md` §3) |

---

## 7. Entry and Exit Criteria

### Entry Criteria (before the test cycle begins)

- The build is deployed to the target environment without errors
- The smoke test (A-01, E-01, S-01) passes manually
- Test data (seed users, sample notebooks) is loaded
- All blocking bugs from the previous cycle are fixed

### Exit Criteria (before release to production)

- All Playwright E2E scenarios pass on staging
- The SonarQube Quality Gate is green
- No open defects with the status `Critical` or `Blocker`
- The manual exploratory testing session is completed with no new critical findings
- The test and coverage report is attached to the release ticket
- Product Owner sign-off
- A rollback plan

---

## 8. Defect Management

| Severity | Definition | Resolution SLA |
|---|---|---|
| **Blocker** | Blocks a core scenario (login, code execution, sharing) | Must be fixed before release |
| **Critical** | A core feature is broken, no workaround | Fix in the current sprint |
| **Major** | A feature is degraded, a workaround exists | Fix in the next sprint |
| **Minor** | Cosmetic, UX polish | Backlog |

Defects are filed in the project task tracker, specifying: reproduction steps, environment, screenshots/logs, severity label.

### Bug Ticket Template

```
**Title:** [Area] Short description of the problem
  Example: [Auth] OTP code is accepted after expiration

**Severity:** Blocker | Critical | Major | Minor

**Environment:** Local | CI | Staging | Production
**Browser (if UI):** Chrome 124 / Firefox 126 / Safari 17
**App version / commit:** abc1234

---

**Reproduction steps:**
1. 
2. 
3. 

**Expected result:**
What should happen.

**Actual result:**
What actually happens.

**Reproducibility:** Always | Intermittent (X/10) | Once

---

**Attachments:**
- [ ] Screenshot or screen recording
- [ ] Browser console log
- [ ] Network requests/responses (HAR or DevTools snapshot)
- [ ] Backend log fragment

**Related test case:** A-04 (if applicable)
```

---

## 9. CI/CD Quality Gates

Every pull request must pass the following checks before merge:

```
1. Lint (ESLint + Ruff) — no errors
2. Unit tests — all pass, coverage ≥ 70%
3. API tests — all pass
4. SonarQube scan — Quality Gate green
5. Playwright E2E (smoke subset) — all pass
```

The full E2E test suite runs nightly against staging and on merge to `main`.

---

## 10. Risks and Mitigations

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Delay in OTP email delivery by the provider | Medium | High | Set the OTP TTL to 10 min; test in sandbox mode; monitor delivery latency |
| JS code escaping the sandbox | Low | High | Use the QuickJS WASM Web Worker sandbox (`docs/execution-architecture.md`) with a strict CSP; include a security review before release |
| Misconfigured JWT secret in AWS | Low | High | Infrastructure-as-code with an automated secret-rotation check in CI |
| Flaky Playwright tests blocking CI | Medium | Medium | Retry policy (2 attempts), a quarantine tag for known flaky tests |
| SonarQube coverage drop after rapid development | Medium | Medium | Coverage diff check at the PR level; block merge if coverage drops > 5% |
| The WASM LLM is not supported by older browsers | Medium | Medium | Verify the compatibility matrix; implement an automatic fallback to the backend when WASM support is absent |
| Uncontrolled OpenAI API costs from heavy fallback usage | Medium | High | Configure spending limits in the OpenAI dashboard; log the source of every LLM request; alert on threshold breaches |
| Silent fallback without notifying the user violates expectations | Medium | Medium | Define a UX policy for each fallback tier; cover scenarios L-02 and L-03 in acceptance tests |
| The LLM generates malicious JS that the user runs | Low | High | Add a warning before running generated code; document it as a known risk in the security review |

---

## 11. Roles and Responsibilities

| Role | Responsibility |
|---|---|
| Developer | Unit tests, fixing lint/SonarQube issues, investigating failed tests, smoke testing |
| QA Engineer | Writing E2E tests (Playwright), manual exploratory testing, defect triage |
| Tech Lead | Quality Gate thresholds, release go decision |
| DevOps | CI pipeline, staging environment, AWS secrets management |
