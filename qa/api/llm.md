# API Test Cases — LLM Proxy

**Feature:** LLM code generation proxy endpoint  
**Base URL:** `https://api.notebook.com`  
**Tool:** pytest + httpx / Bruno  
**Auth:** JWT required unless stated otherwise  
**Priority scope:** Smoke, Regression, Edge

---

## TC-API-LLM-01 — Generate code (backend LLM succeeds)

**Priority:** Smoke  
**Related scenario:** R-10  
**Endpoint:** `POST /llm/generate`

| Field | Value |
|---|---|
| Headers | `Authorization: Bearer <jwt>` |
| Request body | `{ "prompt": "Write a function that adds two numbers" }` |
| Expected status | `200` |
| Expected body | `{ "code": "..." }` |
| Expected headers | `X-LLM-Source: backend` (or similar) |

**Pass criteria:** 200 with generated code in response  
**Fail criteria:** 500, empty code, missing source header

---

## TC-API-LLM-02 — Generate code (backend LLM fails, fallback to OpenAI)

**Priority:** Regression  
**Related scenario:** R-11  
**Endpoint:** `POST /llm/generate`

| Field | Value |
|---|---|
| Precondition | Backend LLM is mocked to fail |
| Expected status | `200` |
| Expected body | `{ "code": "..." }` |
| Expected headers | `X-LLM-Source: openai` |

**Pass criteria:** 200 with code, source header is `openai`  
**Fail criteria:** 503, no fallback triggered, wrong source header

---

## TC-API-LLM-03 — Generate code with empty prompt

**Priority:** Regression  
**Related scenario:** R-12  
**Endpoint:** `POST /llm/generate`

| Field | Value |
|---|---|
| Request body | `{ "prompt": "" }` |
| Expected status | `422` |
| Expected body | Validation error with field details |

**Pass criteria:** 422 with clear validation error  
**Fail criteria:** 200, empty prompt sent to LLM, 500

---

## TC-API-LLM-04 — Generate code without JWT

**Priority:** Regression  
**Related scenario:** R-13  
**Endpoint:** `POST /llm/generate`

| Field | Value |
|---|---|
| Headers | None |
| Request body | `{ "prompt": "Write hello world" }` |
| Expected status | `401` |

**Pass criteria:** 401 returned  
**Fail criteria:** 200, code generated without auth

---

## TC-API-LLM-05 — All LLM tiers exhausted

**Priority:** Regression  
**Related scenario:** R-14  
**Endpoint:** `POST /llm/generate`

| Field | Value |
|---|---|
| Precondition | Backend LLM and OpenAI both mocked to fail |
| Expected status | `503` |
| Expected body | `{ "error": "..." }` — clear error message |

**Pass criteria:** 503 with descriptive error  
**Fail criteria:** 200 with empty code, 500, server crash

---

## TC-API-LLM-06 — Generate code with oversized prompt

**Priority:** Edge  
**Endpoint:** `POST /llm/generate`

| Field | Value |
|---|---|
| Request body | `{ "prompt": "<string > max chars>" }` |
| Expected status | `422` |
| Expected body | Validation error mentioning character limit |

**Pass criteria:** 422 with limit error  
**Fail criteria:** Prompt forwarded to LLM, 500, no validation

---

## TC-API-LLM-07 — Response time within acceptable limit

**Priority:** Edge  
**Endpoint:** `POST /llm/generate`

| Field | Value |
|---|---|
| Request body | `{ "prompt": "Write a simple function" }` |
| Expected | Response within 30 seconds |

**Pass criteria:** Response within 30s  
**Fail criteria:** Timeout, no response within 30s

---

## TC-API-LLM-08 — LLM request logged in audit

**Priority:** Edge  
**Endpoint:** `POST /llm/generate`

| Step | Action | Expected |
|---|---|---|
| 1 | Send a valid generate request | 200 response |
| 2 | Check audit logs (DB or log file) | Entry created with: user_id, model, latency, status, tokens |

**Pass criteria:** Audit entry created with all required fields  
**Fail criteria:** No log entry, missing fields, wrong user_id logged

---

## TC-API-LLM-09 — Per-user rate limit exceeded (429)

**Priority:** Regression  
**Related scenario:** `qa/ui/ai-code-generation.md` TC-AI-B-08  
**Endpoint:** `POST /api/v1/llm/generate`

| Field | Value |
|---|---|
| Precondition | User has already made the maximum allowed requests within the rate-limit window (`ai-architecture.md` §8.3, 20 req/min/user) |
| Request body | `{ "prompt": "Write a simple function", "mode": "generate", "language": "javascript" }` |
| Expected status | `429` |
| Expected headers | `Retry-After: <seconds>` |
| Expected body (current) | `{ "error": { "code": "rate_limited", "message": "...", "fields": {} } }` — the standard error envelope (`api/app/core/errors.py`) |
| Expected body (future, `ai-architecture.md` §5.2) | adds `tier: "backend"` and `requestId: "uuid"` alongside `error` — not yet returned by the current envelope |

**Pass criteria:** `429` with `error.code == "rate_limited"`, `Retry-After` header present  
**Fail criteria:** `200` despite exceeding the limit, generic `5xx`, missing `Retry-After`
