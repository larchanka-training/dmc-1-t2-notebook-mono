# E2E Autotest Tasks — JS Notebook SaaS

Tasks for implementing E2E autotests using Playwright.  
Each task corresponds to a single spec file. Priorities: **Smoke** (blocks CI on every PR), **Regression** (nightly run and merge into `main`), **Edge** (nightly run, a separate schedule is acceptable).

---

## Implementation status (issue #157)

A standalone automation project now implements this roadmap (plus a black-box API
suite) under one Allure report: [`autotests/`](../../autotests/). Status and
traceability live in [`autotests/TRACEABILITY.md`](../../autotests/TRACEABILITY.md);
the release-certification run is in [`docs/qa/qa-info.md`](qa-info.md).

Two roadmap items **drifted from the implemented product** (code is the source of
truth, `AGENTS.md` §12) and are therefore documented skips, not active tests:

- **Sharing (`AT-SH-01..04`)** — the sharing feature is **not implemented** in
  either `ui` or `api` (no generate/revoke UI, no share endpoints; notebooks are
  owner-scoped). The specs are kept as skipped placeholders.
- **LLM (`AT-LLM-01..07`)** — the implemented UI generates code **in-browser via
  WebLLM**, not through the backend `/llm/generate` proxy, so the `mockWasmLlm` /
  fallback-chain specs don't match reality. The backend endpoint is covered at the
  API contract level instead (auth + prompt validation; real generation needs
  Bedrock). Also note the route surface is `/login` + `/` (no `/dashboard`).

The smoke + regression subset for **auth**, **notebook editor** and **code
execution** is implemented against the real UI selectors.

---

## Summary table

| ID | Feature | Priority | File |
|---|---|---|---|
| AT-INFRA-01 | Infrastructure | — | `e2e/fixtures/index.ts` |
| AT-INFRA-02 | Infrastructure | — | `e2e/pages/` |
| AT-AUTH-01 | Authentication | Smoke | `e2e/auth/otp-login.spec.ts` |
| AT-AUTH-02 | Authentication | Regression | `e2e/auth/otp-invalid.spec.ts` |
| AT-AUTH-03 | Authentication | Regression | `e2e/auth/otp-expired.spec.ts` |
| AT-AUTH-04 | Authentication | Regression | `e2e/auth/otp-resend-throttle.spec.ts` |
| AT-AUTH-05 | Authentication | Regression | `e2e/auth/unauthenticated-redirect.spec.ts` |
| AT-AUTH-06 | Authentication | Edge | `e2e/auth/jwt-expiry.spec.ts` |
| AT-AUTH-07 | Authentication | Edge | `e2e/auth/email-enumeration.spec.ts` |
| AT-NB-01 | Editor | Smoke | `e2e/notebook/create.spec.ts` |
| AT-NB-02 | Editor | Regression | `e2e/notebook/rename.spec.ts` |
| AT-NB-03 | Editor | Regression | `e2e/notebook/save-persist.spec.ts` |
| AT-NB-04 | Editor | Regression | `e2e/notebook/delete.spec.ts` |
| AT-NB-05 | Editor | Regression | `e2e/notebook/multi-notebook-nav.spec.ts` |
| AT-EX-01 | Code execution | Smoke | `e2e/execution/console-log.spec.ts` |
| AT-EX-02 | Code execution | Regression | `e2e/execution/syntax-error.spec.ts` |
| AT-EX-03 | Code execution | Regression | `e2e/execution/infinite-loop-timeout.spec.ts` |
| AT-EX-04 | Code execution | Edge | `e2e/execution/sandbox-fetch-policy.spec.ts` |
| AT-SH-01 | Sharing | Smoke | `e2e/sharing/generate-and-open.spec.ts` |
| AT-SH-02 | Sharing | Regression | `e2e/sharing/guest-execution.spec.ts` |
| AT-SH-03 | Sharing | Regression | `e2e/sharing/revoke.spec.ts` |
| AT-SH-04 | Sharing | Edge | `e2e/sharing/deleted-notebook-link.spec.ts` |
| AT-LLM-01 | LLM | Smoke | `e2e/llm/wasm-happy-path.spec.ts` |
| AT-LLM-02 | LLM | Regression | `e2e/llm/fallback-to-backend.spec.ts` |
| AT-LLM-03 | LLM | Regression | `e2e/llm/fallback-to-openai.spec.ts` |
| AT-LLM-04 | LLM | Regression | `e2e/llm/all-levels-fail.spec.ts` |
| AT-LLM-05 | LLM | Regression | `e2e/llm/prompt-validation.spec.ts` |
| AT-LLM-06 | LLM | Edge | `e2e/llm/wasm-loading-state.spec.ts` |
| AT-LLM-07 | LLM | Edge | `e2e/llm/no-wasm-support.spec.ts` |

**Total:** 2 infrastructure + 7 Auth + 5 Notebook + 4 Execution + 4 Sharing + 7 LLM = **29 tasks**  
**Smoke (block PRs):** AT-AUTH-01, AT-NB-01, AT-EX-01, AT-SH-01, AT-LLM-01

---

## Infrastructure and general setup

### AT-INFRA-01 — Base fixtures and helpers

**Priority:** Infrastructure (do first)  
**File:** `e2e/fixtures/index.ts`

**What to implement:**
- Fixture `authenticatedPage` — opens the page with a JWT already set (via `page.addInitScript` or `storageState`), so that the OTP flow does not have to run in every test
- Helper `interceptOtp(page)` — intercepts the `POST /auth/request-otp` response and extracts the OTP from the response body (email sandbox mode)
- Helper `seedNotebook(apiContext, title?, code?)` — creates a notebook via the API and returns its `id`
- Helper `mockWasmLlm(page, { canHandle, response })` — stubs the WASM LLM via `page.addInitScript` to control behavior in LLM tests

**Dependencies:** Must be done before all other tasks.

---

### AT-INFRA-02 — Page Object Model

**Priority:** Infrastructure  
**File:** `e2e/pages/`

**What to implement:**

| Class | File | Responsibility |
|---|---|---|
| `LoginPage` | `login.page.ts` | Email field, request OTP button, OTP field, confirm button, error messages |
| `DashboardPage` | `dashboard.page.ts` | Sidebar with the notebook list, create button, navigation |
| `NotebookPage` | `notebook.page.ts` | Code editor, run button, output panel, save button, title field |
| `SharePage` | `share.page.ts` | Generate link button, URL display, revoke button |
| `LlmPromptPanel` | `llm-prompt.page.ts` | Prompt field, generate button, character counter, loading indicator, error message |

---

## Feature 1: Authentication

### AT-AUTH-01 — Full OTP login scenario

**Priority:** Smoke  
**File:** `e2e/auth/otp-login.spec.ts`  
**QA scenarios:** A-01, A-02

**What to automate:**
1. Open the login page
2. Enter a valid email, click "Get code"
3. Intercept the OTP via `interceptOtp(page)`
4. Enter the OTP, confirm
5. Verify the redirect and the presence of the JWT

**Assertions:**
- The URL switches to `/dashboard`
- The JWT is present in `localStorage` or a cookie
- The sidebar/dashboard is rendered without console errors

**Setup:** seed user, email sandbox enabled in the staging config

---

### AT-AUTH-02 — Invalid OTP

**Priority:** Regression  
**File:** `e2e/auth/otp-invalid.spec.ts`  
**QA scenarios:** A-03

**What to automate:**
1. Request an OTP for a valid email
2. Enter a deliberately invalid code (for example, `000000`)
3. Check the error message
4. Confirm that a second attempt with the correct OTP still works (the OTP was not "burned")

**Assertions:**
- An inline error message is shown
- The URL stays on the login page
- After entering the correct OTP, login succeeds

---

### AT-AUTH-03 — Expired OTP

**Priority:** Regression  
**File:** `e2e/auth/otp-expired.spec.ts`  
**QA scenarios:** A-04

**What to automate:**
1. Mock the `POST /auth/verify-otp` endpoint — return a `401` response with the body `{ error: "otp_expired" }`
2. Enter any OTP
3. Verify that the expiration message and the resend button are displayed

**Assertions:**
- Text about the code expiration is shown
- The "Resend" button is visible and active

**Note:** Do not manipulate the system clock — use an API mock.

---

### AT-AUTH-04 — OTP resend throttle

**Priority:** Regression  
**File:** `e2e/auth/otp-resend-throttle.spec.ts`  
**QA scenarios:** A-05

**What to automate:**
1. Request an OTP
2. Immediately click "Resend" (without waiting for the timer to expire)
3. Verify that the button is disabled and a countdown is shown

**Assertions:**
- The resend button is disabled
- A countdown timer with a decreasing number of seconds is visible

---

### AT-AUTH-05 — Unauthenticated user redirect

**Priority:** Regression  
**File:** `e2e/auth/unauthenticated-redirect.spec.ts`  
**QA scenarios:** A-06

**What to automate:**
1. Open `/dashboard`, `/notebooks/any-id` without a JWT in storage
2. Confirm the redirect to the login page

**Assertions:**
- The URL switches to `/login` (or equivalent)
- The login page is rendered

---

### AT-AUTH-06 — JWT expiration mid-session

**Priority:** Edge  
**File:** `e2e/auth/jwt-expiry.spec.ts`  
**QA scenarios:** A-07

**What to automate:**
1. Log in via the `authenticatedPage` fixture
2. Use `page.evaluate` to overwrite the JWT in storage with an expired token
3. Perform an action that requires authorization (for example, save the notebook)
4. Verify the behavior: silent token refresh or redirect to login

**Assertions:**
- Either the token refresh request is performed automatically and the action completes
- Or the user is redirected to the login page, with the current URL preserved for returning afterward

---

### AT-AUTH-07 — OTP for a non-existent email (enumeration protection)

**Priority:** Edge  
**File:** `e2e/auth/email-enumeration.spec.ts`  
**QA scenarios:** A-08

**What to automate:**
1. Request an OTP for a non-existent email
2. Request an OTP for an existing email
3. Compare the UI responses — they must be identical

**Assertions:**
- Both requests show the same message (for example, "If the email is registered, you will receive a code")
- The response time is visually indistinguishable (no early reject for a non-existent email)

---

## Feature 2: Notebook editor

### AT-NB-01 — Creating a new notebook

**Priority:** Smoke  
**File:** `e2e/notebook/create.spec.ts`  
**QA scenarios:** E-01

**What to automate:**
1. Log in (fixture), go to the dashboard
2. Click "Create notebook"
3. Confirm that the editor opened with empty content

**Assertions:**
- The URL contains the new notebook's id
- The editor is empty
- The default title is present in the sidebar
- 2 seconds after creation — the notebook appears in the `GET /notebooks` response (check via `apiContext`)

---

### AT-NB-02 — Renaming a notebook

**Priority:** Regression  
**File:** `e2e/notebook/rename.spec.ts`  
**QA scenarios:** E-05

**What to automate:**
1. Create a notebook via `seedNotebook`
2. Open the notebook, click on the title, enter a new name, confirm
3. Reload the page

**Assertions:**
- The new name is displayed in the editor title after confirmation
- The new name is displayed in the sidebar
- After reload, the name is preserved

---

### AT-NB-03 — Manual save and persistence

**Priority:** Regression  
**File:** `e2e/notebook/save-persist.spec.ts`  
**QA scenarios:** E-04

**What to automate:**
1. Open the notebook, enter code
2. Click the save button
3. Confirm the toast notification
4. Reload the page, confirm that the code was preserved

**Assertions:**
- A "Saved" toast (or equivalent) appears and disappears
- After `page.reload()`, the code in the editor matches what was entered

---

### AT-NB-04 — Deleting a notebook

**Priority:** Regression  
**File:** `e2e/notebook/delete.spec.ts`  
**QA scenarios:** E-06

**What to automate:**
1. Create two notebooks via `seedNotebook`
2. Delete one of them through the UI
3. Confirm the redirect and its disappearance from the sidebar

**Assertions:**
- The deleted notebook disappears from the sidebar
- The URL switches to the dashboard or the remaining notebook
- `GET /notebooks` does not return the deleted id

---

### AT-NB-05 — Navigation between multiple notebooks

**Priority:** Regression  
**File:** `e2e/notebook/multi-notebook-nav.spec.ts`  
**QA scenarios:** E-07

**What to automate:**
1. Create 3 notebooks with different code via `seedNotebook`
2. Click on them in the sidebar one after another
3. Verify that the editor content changes correctly

**Assertions:**
- The URL updates on each switch
- The editor content corresponds to the selected notebook
- There is no state leakage from the previous notebook

---

## Feature 3: Code execution (sandbox)

### AT-EX-01 — Basic console.log output

**Priority:** Smoke  
**File:** `e2e/execution/console-log.spec.ts`  
**QA scenarios:** X-01

**What to automate:**
1. Open the notebook, enter `console.log("hello")`
2. Click "Run"
3. Check the output panel

**Assertions:**
- The output panel contains the string `hello`
- There are no errors in the browser console

---

### AT-EX-02 — Syntax error before execution

**Priority:** Regression  
**File:** `e2e/execution/syntax-error.spec.ts`  
**QA scenarios:** X-04

**What to automate:**
1. Enter code with a syntax error (for example, `const x = {`)
2. Click "Run"
3. Confirm that the parsing error is displayed before the execution attempt

**Assertions:**
- The output panel or an inline editor indicator shows `SyntaxError`
- The application does not crash, the run button remains available

---

### AT-EX-03 — Infinite loop timeout

**Priority:** Regression  
**File:** `e2e/execution/infinite-loop-timeout.spec.ts`  
**QA scenarios:** X-02

**What to automate:**
1. Enter `while(true) {}`
2. Click "Run"
3. Wait for the timeout (do not hang)

**Assertions:**
- After `N` seconds (per the documented timeout), execution is aborted
- A message about exceeding the execution time is shown
- The page remains responsive (a Playwright `page.click` on another element succeeds)

**Note:** Set `test.setTimeout` with a margin relative to the sandbox timeout.

---

### AT-EX-04 — Sandbox policy for fetch()

**Priority:** Edge  
**File:** `e2e/execution/sandbox-fetch-policy.spec.ts`  
**QA scenarios:** X-03

**What to automate:**
1. Enter `fetch("https://example.com").then(r => console.log(r.status))`
2. Run
3. Record the actual result

**Assertions:**
- If fetch is allowed: the status appears in the output
- If blocked: the output contains an error with clear text (not an unhandled exception)
- The behavior matches the documented sandbox policy

---

## Feature 4: Sharing

### AT-SH-01 — Generating and opening a share link

**Priority:** Smoke  
**File:** `e2e/sharing/generate-and-open.spec.ts`  
**QA scenarios:** S-01, S-02

**What to automate:**
1. Open a notebook with code, generate a share link
2. Copy the URL from the UI
3. Open the URL in a new browser context (without a JWT) via `browser.newContext()`
4. Confirm the read-only mode

**Assertions:**
- The link is unique (contains an id or hash)
- In the guest context, the notebook is displayed
- The edit and save buttons are absent or disabled

---

### AT-SH-02 — Guest runs code in a shared notebook

**Priority:** Regression  
**File:** `e2e/sharing/guest-execution.spec.ts`  
**QA scenarios:** S-03

**What to automate:**
1. Create a notebook with the code `console.log(42)`, get a share link
2. Open the link in a guest context
3. Click "Run"

**Assertions:**
- The output panel shows `42`
- The code in the editor has not changed
- The execution result is not saved to the owner's notebook

---

### AT-SH-03 — Revoking a share link

**Priority:** Regression  
**File:** `e2e/sharing/revoke.spec.ts`  
**QA scenarios:** S-04

**What to automate:**
1. Generate a share link, save the URL
2. Revoke the link through the UI
3. Open the saved URL in a guest context

**Assertions:**
- The page returns a 404 or a "not found" UI message
- The notebook code is not displayed

---

### AT-SH-04 — Share link of a deleted notebook

**Priority:** Edge  
**File:** `e2e/sharing/deleted-notebook-link.spec.ts`  
**QA scenarios:** S-05

**What to automate:**
1. Create a notebook, generate a share link
2. Delete the notebook via the API (`apiContext.delete(...)`)
3. Open the share link in a guest context

**Assertions:**
- A 404 response
- The UI shows a clear message, not a blank screen or a JS error

---

## Feature 5: LLM code generation

### AT-LLM-01 — WASM LLM handles the request (happy path)

**Priority:** Smoke  
**File:** `e2e/llm/wasm-happy-path.spec.ts`  
**QA scenarios:** L-01, L-07

**What to automate:**
1. Mock the WASM LLM via `mockWasmLlm(page, { canHandle: true, response: 'console.log("generated")' })`
2. Enter a prompt, click "Generate"
3. Confirm that the code is inserted into the editor and that no network request to `/llm/generate` was sent

**Assertions:**
- The editor contains the generated code
- `page.route('/llm/generate', ...)` was not invoked (the network was not used)
- The prompt panel is cleared or hidden after insertion

---

### AT-LLM-02 — Fallback to the backend LLM

**Priority:** Regression  
**File:** `e2e/llm/fallback-to-backend.spec.ts`  
**QA scenarios:** L-02

**What to automate:**
1. Mock the WASM LLM with `{ canHandle: false }`
2. Mock `POST /llm/generate` via `page.route` — return `200` with code and the header `X-LLM-Source: backend`
3. Enter a prompt, click "Generate"

**Assertions:**
- The code from the backend response is inserted into the editor
- The user does not see an error message during the process
- The request to `/llm/generate` was made exactly once

---

### AT-LLM-03 — Fallback to the OpenAI API

**Priority:** Regression  
**File:** `e2e/llm/fallback-to-openai.spec.ts`  
**QA scenarios:** L-03

**What to automate:**
1. Mock the WASM LLM with `{ canHandle: false }`
2. Mock `POST /llm/generate` — the first call to the backend LLM returns `503`, the second (OpenAI) returns `200` with the header `X-LLM-Source: openai`
3. Enter a prompt, click "Generate"

**Assertions:**
- The code is inserted into the editor
- If a UI notification about using OpenAI is intended — it is present
- Two requests to `/llm/generate` were made (or one request, but the backend switched over transparently — depends on the implementation)

---

### AT-LLM-04 — All LLM levels unavailable

**Priority:** Regression  
**File:** `e2e/llm/all-levels-fail.spec.ts`  
**QA scenarios:** L-04

**What to automate:**
1. Mock the WASM LLM with `{ canHandle: false }`
2. Mock `POST /llm/generate` — return `503`
3. Enter a prompt, click "Generate"

**Assertions:**
- A clear error message is displayed
- The editor content has not changed
- The "Generate" button is active again after the error

---

### AT-LLM-05 — Prompt validation: empty field and character limit

**Priority:** Regression  
**File:** `e2e/llm/prompt-validation.spec.ts`  
**QA scenarios:** L-05, L-06

**What to automate:**
1. Open the LLM panel
2. Enter nothing — confirm that the button is disabled
3. Enter a string longer than the limit (for example, 2001 characters with a limit of 2000)
4. Confirm the counter with an error and that submission is blocked

**Assertions:**
- With an empty field: the button is `disabled` or clicking it does not send a request
- When the limit is exceeded: the character counter is colored red, the button is `disabled`
- No request to `/llm/generate` or the WASM LLM is made

---

### AT-LLM-06 — WASM LLM not yet loaded on the first request

**Priority:** Edge  
**File:** `e2e/llm/wasm-loading-state.spec.ts`  
**QA scenarios:** L-09

**What to automate:**
1. Slow down WASM LLM initialization via a mock (return a promise with a 3-second delay)
2. Immediately enter a prompt and click "Generate"
3. Confirm the loading indicator
4. After loading completes, confirm that the result appeared without clicking again

**Assertions:**
- While the WASM is loading — a spinner or the text "Loading model..." is visible
- After loading, the code is inserted without additional user actions

---

### AT-LLM-07 — Browser without WASM support

**Priority:** Edge  
**File:** `e2e/llm/no-wasm-support.spec.ts`  
**QA scenarios:** L-10

**What to automate:**
1. Use `page.addInitScript` to remove `WebAssembly` from `window` (simulate the absence of support)
2. Mock `POST /llm/generate` — return `200`
3. Enter a prompt, click "Generate"

**Assertions:**
- The request goes to the backend (WASM was not used)
- The user does not see an error related to WASM
- The code is inserted into the editor

---
