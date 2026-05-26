# Security Test Cases

**Feature:** Auth security, access control, input validation  
**Base URL:** `https://api.notebook.com`, `https://notebook.com`  
**Priority scope:** Regression, Edge

---

## TC-SEC-01 — OTP brute force protection

**Priority:** Regression

| Step | Action | Expected Result |
|---|---|---|
| 1 | Request OTP for a valid email | OTP issued |
| 2 | Send 10+ incorrect OTP attempts in rapid succession | — |
| 3 | Check response after threshold | `429` or `401` with lockout message |
| 4 | Verify valid OTP no longer works during lockout | Temporarily blocked |

**Pass criteria:** Brute force blocked after N attempts  
**Fail criteria:** Unlimited incorrect attempts allowed

---

## TC-SEC-02 — JWT cannot be forged

**Priority:** Regression

| Step | Action | Expected Result |
|---|---|---|
| 1 | Craft a JWT with modified `user_id` claim (wrong signature) | — |
| 2 | Send `GET /notebooks` with forged token | `401` returned |
| 3 | Craft a JWT with `alg: none` attack | — |
| 4 | Send request with none-alg token | `401` returned |

**Pass criteria:** All forged tokens rejected  
**Fail criteria:** Any forged token accepted

---

## TC-SEC-03 — User cannot access another user's notebooks

**Priority:** Regression

| Step | Action | Expected Result |
|---|---|---|
| 1 | Log in as User A, get notebook id | — |
| 2 | Log in as User B | — |
| 3 | Send `GET /notebooks/<user_a_id>` with User B's JWT | `403` or `404` |
| 4 | Send `DELETE /notebooks/<user_a_id>` with User B's JWT | `403` |
| 5 | Send `PATCH /notebooks/<user_a_id>` with User B's JWT | `403` |

**Pass criteria:** All cross-user access returns 403/404  
**Fail criteria:** User B can read or modify User A's data

---

## TC-SEC-04 — SQL injection attempt

**Priority:** Edge

| Step | Action | Expected Result |
|---|---|---|
| 1 | Send `POST /auth/request-otp` with body `{ "email": "' OR 1=1 --" }` | `422` validation error |
| 2 | Send `GET /notebooks/1' OR '1'='1` | `404` or `422`, no DB data leaked |
| 3 | Check response body | No SQL error details exposed |

**Pass criteria:** Inputs sanitized, no SQL errors in response  
**Fail criteria:** SQL error details in response, 500, data returned

---

## TC-SEC-05 — XSS in notebook content

**Priority:** Regression

| Step | Action | Expected Result |
|---|---|---|
| 1 | Create notebook with title `<script>alert(1)</script>` | — |
| 2 | View notebook in browser | Script not executed |
| 3 | Share notebook, view as guest | Script not executed in guest view |
| 4 | Check page source | Title is HTML-escaped |

**Pass criteria:** Script not executed, content escaped  
**Fail criteria:** Alert fires, script executes in any context

---

## TC-SEC-06 — Sensitive data not exposed in API responses

**Priority:** Regression

| Step | Action | Expected Result |
|---|---|---|
| 1 | Call `GET /notebooks` | — |
| 2 | Inspect response body | No `password_hash`, `otp`, `session_token` fields |
| 3 | Call `POST /auth/verify-otp` | — |
| 4 | Inspect response | No raw OTP in response |

**Pass criteria:** No sensitive fields in any API response  
**Fail criteria:** Hash, OTP, or raw token exposed

---

## TC-SEC-07 — HTTPS enforced, HTTP redirects

**Priority:** Regression

| Step | Action | Expected Result |
|---|---|---|
| 1 | Open `http://notebook.com` | Redirect to `https://notebook.com` |
| 2 | Open `http://api.notebook.com/notebooks` | Redirect to HTTPS or `400` |
| 3 | Check cookies | `Secure` and `HttpOnly` flags set |

**Pass criteria:** All traffic forced to HTTPS, cookies secured  
**Fail criteria:** HTTP works without redirect, cookies without Secure flag

---

## TC-SEC-08 — Session revocation (logout)

**Priority:** Regression

| Step | Action | Expected Result |
|---|---|---|
| 1 | Log in, save JWT | — |
| 2 | Log out via UI or `POST /auth/logout` | Session marked revoked in DB |
| 3 | Use saved JWT to call `GET /notebooks` | `401` returned |

**Pass criteria:** Revoked JWT rejected  
**Fail criteria:** Old JWT still works after logout
