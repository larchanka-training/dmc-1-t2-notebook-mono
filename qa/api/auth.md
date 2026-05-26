# API Test Cases — Authentication

**Feature:** OTP Auth, JWT issuance, token refresh  
**Base URL:** `https://api.notebook.com`  
**Tool:** pytest + httpx / Bruno  
**Priority scope:** Smoke, Regression, Edge

---

## TC-API-AUTH-01 — Request OTP with valid email

**Priority:** Smoke  
**Related scenario:** R-01  
**Endpoint:** `POST /auth/request-otp`

| Field | Value |
|---|---|
| Request body | `{ "email": "valid@example.com" }` |
| Expected status | `200` |
| Expected body | `{ "message": "..." }` (non-revealing message) |
| Expected headers | `Content-Type: application/json` |

**Pass criteria:** 200 returned, OTP email queued  
**Fail criteria:** 500, 422, or any error for a valid email format

---

## TC-API-AUTH-02 — Request OTP with invalid email format

**Priority:** Regression  
**Related scenario:** R-02  
**Endpoint:** `POST /auth/request-otp`

| Field | Value |
|---|---|
| Request body | `{ "email": "not-an-email" }` |
| Expected status | `422` |
| Expected body | Validation error with field details |

**Pass criteria:** 422 with validation error body  
**Fail criteria:** 200 returned, 500, OTP sent for invalid format

---

## TC-API-AUTH-03 — Request OTP with empty body

**Priority:** Regression  
**Endpoint:** `POST /auth/request-otp`

| Field | Value |
|---|---|
| Request body | `{}` |
| Expected status | `422` |

**Pass criteria:** 422 validation error  
**Fail criteria:** 200, 500, server crashes

---

## TC-API-AUTH-04 — Verify correct OTP

**Priority:** Smoke  
**Related scenario:** R-03  
**Endpoint:** `POST /auth/verify-otp`

| Field | Value |
|---|---|
| Request body | `{ "email": "valid@example.com", "otp": "<valid_otp>" }` |
| Expected status | `200` |
| Expected body | `{ "access_token": "...", "token_type": "bearer" }` |
| Expected headers | `Content-Type: application/json` |

**Pass criteria:** 200 with JWT in response  
**Fail criteria:** 401, 500, no token in response

---

## TC-API-AUTH-05 — Verify incorrect OTP

**Priority:** Regression  
**Related scenario:** R-04  
**Endpoint:** `POST /auth/verify-otp`

| Field | Value |
|---|---|
| Request body | `{ "email": "valid@example.com", "otp": "000000" }` |
| Expected status | `401` |
| Expected body | Error message (not revealing actual OTP) |

**Pass criteria:** 401 returned, no token issued  
**Fail criteria:** 200 returned, 500, JWT issued on wrong OTP

---

## TC-API-AUTH-06 — Verify expired OTP

**Priority:** Regression  
**Related scenario:** A-04  
**Endpoint:** `POST /auth/verify-otp`

| Field | Value |
|---|---|
| Request body | `{ "email": "valid@example.com", "otp": "<expired_otp>" }` |
| Expected status | `401` |
| Expected body | `{ "error": "otp_expired" }` or equivalent |

**Pass criteria:** 401 with expiry error code  
**Fail criteria:** 200, OTP accepted after TTL

---

## TC-API-AUTH-07 — Access protected endpoint with valid JWT

**Priority:** Smoke  
**Endpoint:** `GET /notebooks`

| Field | Value |
|---|---|
| Headers | `Authorization: Bearer <valid_jwt>` |
| Expected status | `200` |

**Pass criteria:** 200 with notebook list  
**Fail criteria:** 401, 403, 500

---

## TC-API-AUTH-08 — Access protected endpoint without JWT

**Priority:** Regression  
**Related scenario:** R-06  
**Endpoint:** `GET /notebooks`

| Field | Value |
|---|---|
| Headers | None |
| Expected status | `401` |

**Pass criteria:** 401 returned  
**Fail criteria:** 200, 403, data returned without auth

---

## TC-API-AUTH-09 — Access protected endpoint with expired JWT

**Priority:** Edge  
**Endpoint:** `GET /notebooks`

| Field | Value |
|---|---|
| Headers | `Authorization: Bearer <expired_jwt>` |
| Expected status | `401` |

**Pass criteria:** 401 returned  
**Fail criteria:** 200, expired token accepted

---

## TC-API-AUTH-10 — OTP rate limiting

**Priority:** Edge  
**Endpoint:** `POST /auth/request-otp`

| Step | Action | Expected Result |
|---|---|---|
| 1 | Send 5+ OTP requests in rapid succession for same email | — |
| 2 | Check response on 6th request | `429 Too Many Requests` |
| 3 | Check headers | `Retry-After` header present |

**Pass criteria:** 429 after threshold  
**Fail criteria:** All requests succeed, no rate limiting
