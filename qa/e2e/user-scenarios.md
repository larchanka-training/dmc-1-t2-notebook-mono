# E2E Test Cases — User Scenarios

**Feature:** Full end-to-end user flows  
**Tool:** Playwright  
**Browsers:** Chromium, Firefox, WebKit  
**Viewport:** 1280x800  
**Environments:** Staging (primary), Local

---

## TC-E2E-01 — Full registration and login flow

**Priority:** Smoke  
**Related scenarios:** A-01, A-02

| Step | Action | Expected Result |
|---|---|---|
| 1 | Open `https://notebook.com` | Landing or login page shown |
| 2 | Enter a valid new email, click "Get code" | OTP field appears |
| 3 | Retrieve OTP from email sandbox | OTP obtained |
| 4 | Enter OTP, click "Confirm" | Redirect to `/dashboard` |
| 5 | Verify JWT in storage | JWT present |
| 6 | Verify dashboard renders | Sidebar visible, no console errors |

**Pass criteria:** Full login completed, dashboard loaded  
**Fail criteria:** Any step fails, stuck on login page

---

## TC-E2E-02 — Create, edit, save, and reload notebook

**Priority:** Smoke  
**Related scenarios:** E-01, E-04

| Step | Action | Expected Result |
|---|---|---|
| 1 | Log in | Dashboard shown |
| 2 | Click "Create notebook" | Empty editor opens |
| 3 | Type `console.log("e2e test")` | Code in editor |
| 4 | Click "Run" | Output shows `e2e test` |
| 5 | Click "Save" | Toast appears |
| 6 | Reload page | Code still in editor |
| 7 | Click "Run" again | Output shows `e2e test` |

**Pass criteria:** Data persists across reload, execution works  
**Fail criteria:** Code lost on reload, execution broken

---

## TC-E2E-03 — Full sharing flow

**Priority:** Smoke  
**Related scenarios:** S-01, S-02, S-03

| Step | Action | Expected Result |
|---|---|---|
| 1 | Log in, create notebook with `console.log(99)` | — |
| 2 | Generate share link | URL obtained |
| 3 | Open share URL in new incognito context | Notebook displayed read-only |
| 4 | Click "Run" as guest | Output shows `99` |
| 5 | Return to owner context, revoke link | Link marked revoked |
| 6 | Open same URL in guest context | 404 or not-found message |

**Pass criteria:** Sharing works, revocation works  
**Fail criteria:** Guest can edit, revoke doesn't work, wrong output

---

## TC-E2E-04 — Complete LLM code generation flow

**Priority:** Smoke  
**Related scenarios:** L-01, L-07

| Step | Action | Expected Result |
|---|---|---|
| 1 | Log in, open a notebook | Editor visible |
| 2 | Open LLM prompt panel | Prompt field visible |
| 3 | Enter "Write a function to reverse a string" | — |
| 4 | Click "Generate" | Loading shown |
| 5 | Wait for completion | Code inserted into editor |
| 6 | Click "Run" | Code executes without errors |

**Pass criteria:** Code generated, inserted, and runnable  
**Fail criteria:** No code inserted, execution fails, app hangs

---

## TC-E2E-05 — Multi-notebook management

**Priority:** Regression  
**Related scenarios:** E-07, E-05, E-06

| Step | Action | Expected Result |
|---|---|---|
| 1 | Log in, create notebook "Alpha" with `console.log("alpha")` | — |
| 2 | Create notebook "Beta" with `console.log("beta")` | — |
| 3 | Navigate to Alpha from sidebar | Editor shows Alpha content |
| 4 | Navigate to Beta | Editor shows Beta content |
| 5 | Rename Beta to "Beta Renamed" | Title updates everywhere |
| 6 | Delete Alpha | Sidebar shows only "Beta Renamed" |
| 7 | Navigate to Beta Renamed | Editor loads correctly |

**Pass criteria:** All CRUD operations work, no state bleed  
**Fail criteria:** Wrong content shown, rename/delete fails

---

## TC-E2E-06 — OTP auth edge cases flow

**Priority:** Regression  
**Related scenarios:** A-03, A-04, A-05

| Step | Action | Expected Result |
|---|---|---|
| 1 | Open login page, request OTP | OTP field shown |
| 2 | Enter wrong OTP `000000` | Error shown, OTP not consumed |
| 3 | Enter correct OTP | Login succeeds |
| 4 | Log out, request new OTP | — |
| 5 | Immediately click "Resend" | Resend blocked with countdown |
| 6 | Wait for countdown, resend | New OTP sent |

**Pass criteria:** Bad OTP rejected, resend throttle works  
**Fail criteria:** Bad OTP accepted, resend not throttled

---

## TC-E2E-07 — Unauthenticated access and redirect

**Priority:** Regression  
**Related scenario:** A-06

| Step | Action | Expected Result |
|---|---|---|
| 1 | Clear all browser storage | — |
| 2 | Navigate to `/dashboard` | Redirect to `/login` |
| 3 | Navigate to `/notebooks/test-id` | Redirect to `/login` |
| 4 | Log in | Redirected back to original URL (or dashboard) |

**Pass criteria:** Protected routes redirect, return URL works  
**Fail criteria:** Protected page accessible without auth

---

## TC-E2E-08 — Code execution sandbox safety

**Priority:** Regression  
**Related scenarios:** X-02, X-04

| Step | Action | Expected Result |
|---|---|---|
| 1 | Log in, create notebook | Editor visible |
| 2 | Enter `const x = {` (syntax error) | — |
| 3 | Click "Run" | SyntaxError shown, app not crashed |
| 4 | Replace with `while(true) {}` | — |
| 5 | Click "Run" | Timeout error after N seconds, page responsive |
| 6 | Interact with the editor | Still functional |

**Pass criteria:** Both error types handled gracefully  
**Fail criteria:** App crashes, page hangs, no error messages
