# UI Test Cases — Authentication

**Feature:** OTP Login Flow  
**Stack:** React / TypeScript  
**Priority scope:** Smoke, Regression, Edge

---

## TC-UI-AUTH-01 — Request OTP with valid email

**Priority:** Smoke  
**Related scenario:** A-01

| Step | Action | Expected Result |
|---|---|---|
| 1 | Open `https://notebook.com/login` | Login page renders, email input is visible |
| 2 | Enter a valid registered email | Input accepts text |
| 3 | Click "Get code" button | Button shows loading state |
| 4 | Wait up to 60 seconds | OTP input field appears, success message shown |
| 5 | Check email inbox | OTP email arrives within 60 sec |

**Pass criteria:** OTP field is visible, email arrives within 60 sec  
**Fail criteria:** Button stays loading indefinitely, email not received, error shown for valid email

---

## TC-UI-AUTH-02 — Login with correct OTP

**Priority:** Smoke  
**Related scenario:** A-02

| Step | Action | Expected Result |
|---|---|---|
| 1 | Complete TC-UI-AUTH-01 | OTP field is visible |
| 2 | Enter correct OTP from email | OTP accepted |
| 3 | Click "Confirm" | Loading indicator shown |
| 4 | Observe redirect | User is redirected to `/dashboard` |
| 5 | Check browser storage | JWT is present in localStorage or cookie |
| 6 | Inspect page | Dashboard/sidebar rendered without console errors |

**Pass criteria:** Redirect to dashboard, JWT present, no errors  
**Fail criteria:** Stays on login page, no JWT, console errors

---

## TC-UI-AUTH-03 — Login with incorrect OTP

**Priority:** Regression  
**Related scenario:** A-03

| Step | Action | Expected Result |
|---|---|---|
| 1 | Complete TC-UI-AUTH-01 | OTP field is visible |
| 2 | Enter invalid OTP (e.g. `000000`) | Input accepts text |
| 3 | Click "Confirm" | Inline error message shown |
| 4 | Verify URL | Stays on login page |
| 5 | Enter correct OTP from email | Login succeeds (OTP not consumed by bad attempt) |

**Pass criteria:** Error shown, OTP not burned, valid OTP still works  
**Fail criteria:** Redirect on wrong OTP, OTP consumed by wrong attempt, no error message

---

## TC-UI-AUTH-04 — Login with expired OTP

**Priority:** Regression  
**Related scenario:** A-04

| Step | Action | Expected Result |
|---|---|---|
| 1 | Request an OTP | OTP field visible |
| 2 | Wait > 10 minutes (or use mocked expired response) | — |
| 3 | Enter any OTP | Submit |
| 4 | Observe UI | "Code expired" message shown |
| 5 | Check UI controls | "Resend" button is visible and clickable |

**Pass criteria:** Expiry message shown, resend button visible  
**Fail criteria:** Login succeeds with expired OTP, no message, app crashes

---

## TC-UI-AUTH-05 — OTP resend throttle

**Priority:** Regression  
**Related scenario:** A-05

| Step | Action | Expected Result |
|---|---|---|
| 1 | Request OTP | OTP field visible |
| 2 | Immediately click "Resend" | Resend is blocked |
| 3 | Check UI | Resend button is disabled, countdown timer visible |
| 4 | Wait for countdown to expire | Resend button becomes enabled |

**Pass criteria:** Button disabled with visible countdown  
**Fail criteria:** Multiple OTPs sent, no throttle, no countdown shown

---

## TC-UI-AUTH-06 — Redirect unauthenticated user from protected route

**Priority:** Regression  
**Related scenario:** A-06

| Step | Action | Expected Result |
|---|---|---|
| 1 | Ensure no JWT in browser storage | — |
| 2 | Navigate directly to `/dashboard` | Redirect to `/login` |
| 3 | Navigate directly to `/notebooks/any-id` | Redirect to `/login` |
| 4 | Check login page | Login page renders correctly |

**Pass criteria:** Protected routes redirect to login  
**Fail criteria:** Protected page loads without auth, blank page, 500 error

---

## TC-UI-AUTH-07 — JWT expiration mid-session

**Priority:** Edge  
**Related scenario:** A-07

| Step | Action | Expected Result |
|---|---|---|
| 1 | Log in successfully | Dashboard shown |
| 2 | Overwrite JWT in storage with expired token | — |
| 3 | Perform an authenticated action (e.g., save notebook) | — |
| 4 | Observe behavior | Either: token silently refreshed and action completes, OR: redirect to login with return URL preserved |

**Pass criteria:** No silent failure, graceful handling  
**Fail criteria:** Action fails silently, blank screen, unhandled error shown to user

---

## TC-UI-AUTH-08 — OTP for non-existent email (no user enumeration)

**Priority:** Edge  
**Related scenario:** A-08

| Step | Action | Expected Result |
|---|---|---|
| 1 | Enter a non-existent email, click "Get code" | Generic success-like message shown |
| 2 | Enter a real registered email, click "Get code" | Same message shown |
| 3 | Compare UI responses | Both responses are visually identical |
| 4 | Compare response timing | No significantly faster rejection for non-existent email |

**Pass criteria:** Identical UI response for both cases  
**Fail criteria:** Different messages, different timing revealing account existence
