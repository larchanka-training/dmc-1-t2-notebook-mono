# Authentication Architecture — JS Notebook

> Project-level architectural overview of the authentication subsystem.
> The detailed protocol-level spec lives in `api/docs/auth.md`. This
> document explains **what we have today**, **what we're building**, and
> **how we migrate** — at a level useful for any engineer (FE, BE,
> DevOps, QA) joining the project.

---

## 1. Overview

JS Notebook keeps notebooks scoped per user. To do that safely, every
write or list-by-owner query must run under an authenticated identity.
We chose a deliberately simple auth model: **email + one-time password
(OTP)** for login, **JWT access tokens** with **opaque refresh tokens**
for session continuity, **no third-party OAuth**, no passwords.

The design is split into two layers:

- **Protocol layer** — request/response shapes, JWT format, OTP
  lifecycle, refresh rotation, reuse detection. See `api/docs/auth.md`.
- **Architectural layer** (this document) — the journey from current
  placeholder to target auth, integration with other subsystems, and
  the contract every other component (FE, execution, notebooks, LLM
  proxy) depends on.

---

## 2. Current state (post PR #29, 2026-05-27)

PR #29 shipped the **placeholder** authentication path. It is the
minimum viable contract that unblocks frontend work on notebooks before
real auth lands.

### 2.1 What exists today

| Component | Status |
|---|---|
| `app.users` table (id, email, display_name, created_at) | ✅ Liquibase changeset 0002 |
| Dev-only seed user `00000000-...-0001` | ✅ Liquibase changeset 0002, `context="dev"` only |
| `GET /api/v1/auth/me` | ✅ returns the current user |
| `get_current_user` dependency | ✅ used by every owner-scoped notebook route |
| Placeholder identity via `X-User-Id` header | ✅ accepted in dev/test/local only |
| Env guard — placeholder rejected in non-dev | ✅ returns `501 AUTH_NOT_IMPLEMENTED` |

### 2.2 What placeholder auth means in practice

In `dev` / `local` / `test` environments:

- If the request has no `X-User-Id` header, the API resolves to the
  hardcoded dev user (`00000000-...-0001`).
- If the request supplies a valid UUID in `X-User-Id`, the API uses
  that as the current user — and lazily creates a row in `app.users`
  with synthetic email `<uuid>@dev.notebook.local` if missing. This
  keeps foreign-key constraints on `notebooks.owner_id` from failing.

In any other environment (`production`, `staging`, etc.):

- Every request to `/auth/me` (and by extension every notebook route)
  returns `501` with error code `AUTH_NOT_IMPLEMENTED`. This is a
  fail-closed guard — the placeholder cannot accidentally serve real
  users.

### 2.3 Why placeholder first

- Notebook controllers depend on `get_current_user` from day one. When
  real OTP/JWT lands, **only the dependency implementation changes** —
  no controller touches.
- FE can build the notebook UI against a stable owner-scoped API
  without waiting for the auth team to ship.
- The `app.users` table is real; only how we *resolve identity*
  differs between placeholder and target.

---

## 3. Target architecture

> Detailed protocol spec: `api/docs/auth.md`. The summary here is for
> orientation — read the linked doc for exact request/response shapes,
> error codes, and edge cases.

### 3.1 Login flow (OTP)

```
   ┌─────────┐                    ┌─────────────┐
   │   FE    │                    │   API       │
   └────┬────┘                    └──────┬──────┘
        │ POST /auth/otp/request          │
        │ { email }                       │
        │────────────────────────────────▶│
        │                                  │  store hashed OTP,
        │                                  │  send email
        │ 204 (prod) / 200 + otp (dev)    │
        │◀────────────────────────────────│
        │                                  │
        │  user enters OTP                 │
        │                                  │
        │ POST /auth/otp/verify            │
        │ { email, otp }                   │
        │────────────────────────────────▶│
        │                                  │  verify, create session,
        │                                  │  issue tokens
        │ { accessToken, refreshToken,    │
        │   user }                         │
        │◀────────────────────────────────│
        │                                  │
        │ FE stores tokens in localStorage │
```

- **No passwords.** OTP is generated server-side, hashed (sha256 or
  argon2), 5-minute TTL, max 5 failed attempts.
- **User created lazily** on first successful `verify` for an email.
- **Dev mode** returns the OTP in the response body (`{ otp: "123456" }`)
  so FE can complete the flow without an email service.

### 3.2 Session continuity

```
[FE] every request:
       Authorization: Bearer <accessToken>

[FE] on 401 or before exp:
       POST /auth/refresh { refreshToken }
       → { accessToken, refreshToken }   ← rotation

[FE] logout:
       POST /auth/logout { refreshToken } → 204
```

- **Access token** — short-lived JWT (15 min), HS256, signed with
  `JWT_SECRET`. Contains `sub` (user id), `sessionId`, `iat`, `exp`.
  **Not** revocable mid-life — too expensive to check on every request.
- **Refresh token** — opaque random string (32+ bytes, base64url).
  Server stores **hash** in `app.refresh_tokens`. 30-day session
  lifetime. **Rotated on every use** — old token marked `replaced_at`
  and linked to its successor; presenting a rotated token triggers
  family-wide revocation (reuse detection).

### 3.3 Tables introduced by real auth

| Table | Purpose |
|---|---|
| `app.otps` | OTP code hashes, expiry, attempt counter |
| `app.sessions` | One row per authenticated session (device); metadata + `revoked_at` |
| `app.refresh_tokens` | Token family per session; tracks rotation chain and reuse-detection state |

`app.users` already exists from PR #29 — no schema change.

### 3.4 Defense properties

- **Stolen access token** is useful for at most 15 minutes; after `exp`
  the client must refresh, and a revoked session blocks refresh.
- **Stolen refresh token** detected on first reuse: if a legitimate
  client already rotated it, presenting the old one triggers session
  revocation (`refresh_reuse_detected`).
- **Stolen OTP** is single-use, time-limited, and rate-limited per
  email (3 requests / 15 min) and per IP (20 / 15 min).
- **Server breach** does not leak active tokens — only OTP hashes and
  refresh hashes are stored; raw values exist only on the client.

---

## 4. What changes between current and target

| Concern | Current (placeholder) | Target (OTP+JWT) |
|---|---|---|
| Identity source | `X-User-Id` header | JWT `sub` claim |
| User creation | Lazy from any valid UUID | Lazy on first OTP verify |
| Token lifetime | None | 15 min access + 30 d refresh |
| Logout | None (header removal) | Server-side session revocation |
| Email service | None | Pluggable provider (SendGrid / Resend / etc.) |
| Tables needed | `users` only | `users` + `otps` + `sessions` + `refresh_tokens` |
| Rate limiting | None | Per-email + per-IP for OTP, per-session for refresh |
| Non-dev environment | Returns 501 | Real auth |
| Dependency `get_current_user` | Reads header, creates synthetic user | Validates JWT, loads session |

**Every notebook controller stays unchanged.** The contract surface for
the rest of the system is just `CurrentUser` — only the resolution
mechanism inside `get_current_user` changes.

---

## 5. Migration plan

The target architecture lands in **four sequential PRs**. Each PR is
independently mergeable and the system remains usable between PRs.

### Phase 1 — Schema & email abstraction (PR-A)
- Liquibase changeset 0003: `otps`, `sessions`, `refresh_tokens`.
- `EmailService` interface + `NoopEmailService` (logs to structlog) for
  dev/local/test; one real implementation stub (SendGrid recommended).
- Config: `JWT_SECRET`, `JWT_ACCESS_TTL_SECONDS=900`,
  `JWT_REFRESH_TTL_SECONDS=2592000`, `OTP_TTL_SECONDS=300`,
  `OTP_MAX_ATTEMPTS=5`, `EMAIL_PROVIDER`, `EMAIL_PROVIDER_API_KEY`,
  `EMAIL_FROM`.
- No new endpoints yet — just plumbing.

### Phase 2 — OTP endpoints (PR-B)
- `POST /api/v1/auth/otp/request`
- `POST /api/v1/auth/otp/verify` — returns `{ accessToken, refreshToken, user }`.
- JWT issue / parse helpers (HS256).
- Dev mode returns OTP in response body; prod returns `204`.
- **Placeholder `X-User-Id` still works in dev/local/test** — the
  routes coexist. This lets FE keep working through the migration.

### Phase 3 — Session continuity (PR-C)
- `POST /api/v1/auth/refresh` (rotation + reuse detection).
- `POST /api/v1/auth/logout` (session-level revocation).
- `get_current_user` upgraded to accept either Bearer JWT or
  `X-User-Id` (dev/local/test only). Order: JWT wins if present.

### Phase 4 — Cutover (PR-D)
- Remove `X-User-Id` path entirely.
- Remove dev-seed user from Liquibase (the now-real OTP flow creates
  users naturally).
- Set `APP_ENV=staging` / `production` in deployment configs — the
  env guard from PR #29 is no longer needed (real auth answers).
- Tighten CORS (`allow_credentials=false` is already correct because
  tokens travel in `Authorization` header, not cookies).

---

## 6. Integration contract

This is the single contract every other subsystem depends on. As long
as `CurrentUser` and the dependency name stay stable, the rest of the
system is unaffected by auth changes.

```python
# app/modules/auth/dependencies.py
def get_current_user(...) -> CurrentUser: ...

# app/modules/auth/schemas/user_schemas.py
class CurrentUser(BaseModel):
    id: UUID
    email: str | None
    display_name: str | None
    roles: list[str]
```

Consumers (`notebooks`, `execution`, future `llm-proxy`) declare
`current_user: CurrentUser = Depends(get_current_user)` and never
inspect tokens, headers, or sessions directly.

---

## 7. Cross-cutting concerns

### 7.1 CORS

FE and API are served from different origins in dev (`localhost:3000`
vs `localhost:8000`). The current CORS allowlist includes the FE
origin and the proxy origin. Auth tokens travel in `Authorization`
header (not cookies), so `allow_credentials=false` is correct and
stays correct under target auth.

### 7.2 LLM proxy

The LLM proxy (separate sprint) will live behind the same auth wall —
`Depends(get_current_user)`. LLM API keys never reach the FE; only
the proxy holds them.

### 7.3 Execution endpoint

If `POST /api/v1/execute` ships (stretch goal), it sits behind the
same auth dependency. The sandbox itself does not need user identity
to function, but billing/audit/rate-limit logic does.

### 7.4 Frontend storage

FE stores `accessToken` and `refreshToken` in `localStorage`. This is
a deliberate trade-off: simpler than cookie + CSRF flow, vulnerable
to XSS — mitigated by strict CSP, no third-party scripts, and short
access TTL. Documented in [UI repo: docs/auth.md].

---

## 8. Out of scope

- **WebAuthn / Passkey support** — placeholder column
  `users.biometric_snapshot` exists for future work.
- **Social login (Google, GitHub)** — explicitly rejected; OTP only.
- **Multi-factor on top of OTP** — single factor (email OTP) for v1.
- **Admin "logout everywhere"** endpoint — requires a separate flow
  with valid access token; not in v1.
- **Audit log table** (`auth_events`) — not in v1; CloudWatch /
  structlog records are sufficient.

---

## 9. Related documents

- `api/docs/auth.md` — protocol-level spec (sources of truth for
  request/response shapes, error codes, edge cases).
- `docs/System_Architecture.md` — overall system architecture.
- `docs/execution-architecture.md` — execution path; relies on this
  auth model.
- `docs/requirements.md` — product requirements (security, RBAC).
- `_private/drafts/spec-auth-ru.md` — educational extended Russian
  version of this document.

[UI repo: docs/auth.md]: https://github.com/larchanka-training/dmc-1-t2-notebook-ui/blob/main/docs/auth.md
