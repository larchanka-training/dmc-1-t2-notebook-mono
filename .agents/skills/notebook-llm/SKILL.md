---
name: notebook-llm
description: >
  Project-specific guide for the LLM code-generation feature of JS
  Notebook — the three-tier fallback chain (WASM in browser → backend
  proxy → OpenAI API), API-key handling, prompt validation, rate
  limits, streaming, and UX policy on silent vs. notified fallback.
  Load this skill whenever a task touches the `/llm/generate` path,
  the prompt builder, the provider abstraction, the WASM LLM client,
  or any code that handles API keys / generated code from the model.
globs:
  - "api/app/modules/llm/**"
  - "ui/src/**/llm/**"
  - "ui/src/features/llm-generate/**"
  - "docs/requirements.md"
---

# notebook-llm

Top-level orientation for any work on the LLM code-generation
feature. The feature is the single most security- and UX-sensitive
flow in this project — secrets, untrusted output, rate limits,
fallback chain, and "user notices the switch?" UX all collide here.

## Overview

The product chain is **WASM (browser) → backend LLM → OpenAI API**,
in that order of preference, with the backend acting as a proxy that
hides the OpenAI key from the client.

Source-of-truth documents:

- `docs/requirements.md` §2.3, §3 — functional + non-functional
  requirements (LLM-01..07, LLM-NF-01..05); prompt format §3.3
- `docs/System_Architecture.md` §LLM proxy — HTTP shape of
  `POST /api/llm/generate`
- `docs/qa/qa-plan.md` §6.6 — L-NN scenarios (WASM happy path,
  fallback to backend, fallback to OpenAI, all-fail, validation)
- `.agents/skills/notebook-qa/references/manual-test-checklist.md`
  §"LLM code generation" — browser-side walk-through

This skill enforces the rules that a generic "add an API endpoint"
or "wire a button" agent would miss.

## Instruction priority

When this skill conflicts with `AGENTS.md`, the canonical docs under
`/docs`, or any submodule's own `AGENTS.md` / `docs/` — follow the
project-specific source. This skill is supplemental.

## When to use

Load whenever the task touches:

- The `POST /api/llm/generate` endpoint or any new LLM endpoint
- The provider abstraction (Anthropic, OpenAI, future providers)
- The WASM LLM client in `ui/`, including loader/state/spinner UX
- The prompt builder (system prompt, neighbour-cell context)
- API-key configuration, env vars, secrets handling for LLM
- Rate limiting / quota / cost-control for LLM calls
- The "generated code" insertion into a notebook cell (output is
  untrusted JS)
- Anything matching qa-plan §6.6 L-NN scenarios

Do **not** use this skill for general FastAPI/React work; load
`notebook-api` / `notebook-ui` for that. This skill is loaded
**in addition** when LLM is touched, not instead.

## Three-tier fallback chain

```
┌────────────────┐    ┌────────────────┐    ┌─────────────────┐
│ Tier 1 (T1)    │    │ Tier 2 (T2)    │    │ Tier 3 (T3)     │
│ WASM in browser│ →  │ Backend LLM    │ →  │ OpenAI API      │
│ (no network)   │    │ (self-hosted   │    │ (paid, external)│
│                │    │  / open weight)│    │                 │
└────────────────┘    └────────────────┘    └─────────────────┘
        ↓                    ↓                       ↓
      L-01,                L-02,                   L-03
      L-09 (warm-up),      L-10 (no WASM)         L-04 (all fail)
```

Rules:

- **T1 is the default**: a request that the WASM model can handle
  must not hit the network. Verifiable in DevTools → Network: no
  `/llm/generate` call (L-01).
- **T2 is the proxy**: the only path where the OpenAI key can be
  used. The frontend must never call OpenAI directly.
- **T3 is the last resort**: triggered when T2 returns 5xx /
  upstream error, not when T2 returns 400 (validation failures
  don't fall through tiers).
- **All-fail (L-04)** returns a clear user-facing error; the editor
  state is not mutated; the Generate button is re-enabled.
- **Silent vs. notified fallback** — qa-plan §10 risk: "Silent
  fallback without notifying the user violates expectations". Define
  per-tier UX explicitly in the PR (a small badge, a tooltip, or
  nothing — but the choice must be intentional).

## Security rules (the ones that hurt most when missed)

These supplement `AGENTS.md` §11 (mandatory secret rules) and
`api/docs/auth.md` for sensitive-data handling.

- **API keys are server-side only.** Per LLM-NF-05: the OpenAI /
  Anthropic key lives in the backend env (`OPENAI_API_KEY`,
  `ANTHROPIC_API_KEY`) and is never sent to the client, never logged
  even at DEBUG level, never echoed in error responses, never
  fixtured in tests.
- **No keys in client bundle.** Verify with a build-output grep
  (`pnpm build && grep -r "sk-" dist/`) when the LLM client is
  touched. A leaked `VITE_*` env var ends up in the JS bundle and
  is effectively published.
- **Prompts are untrusted input.** The user controls the description
  text. Validate **at the api boundary** (length, basic shape) per
  LLM-06 prompt-length limit; don't trust that the client already
  truncated. Don't blindly interpolate user text into provider
  system prompts in a way that lets it escape the system role
  (prompt injection — at minimum, treat any "ignore previous"
  pattern as the prompt content, not as an instruction to the
  model).
- **Generated code is untrusted output.** The chain in qa-plan §10
  flags this: "The LLM generates malicious JS that the user runs"
  (Low × High). Mitigations: insert into the cell **without auto-
  running**; the existing QuickJS WASM sandbox is the
  defence-in-depth boundary
  (`docs/execution-architecture.md`); the UI may show a "review
  before running" hint.
- **No raw prompt or completion in structured logs in `prod`.** Log
  the **metadata** (model, latency, token count, tier hit, user id,
  request id) per LLM-NF-04 — not the body. Prompts may contain
  PII or the user's proprietary code. Dev mode may log the body
  behind a flag, never `prod`.
- **Rate limiting is mandatory.** Per LLM-NF-03: ≤ 20 req/min/user
  on `/llm/generate`. Returns 429 with `Retry-After` header. The
  WASM tier must also self-throttle to avoid burning the user's
  CPU on accidental rapid clicks.
- **Quota / cost-control on T3.** OpenAI calls cost real money;
  qa-plan §10 flags "Uncontrolled OpenAI API costs from heavy
  fallback usage" (Medium × High). Per-user daily quota +
  per-deployment global ceiling + alert on threshold breach.

## API contract (HTTP shape)

`POST /api/v1/llm/generate` (placeholder path; align with
`api/docs/openapi.json` when the endpoint lands).

Request body (per `requirements.md` §3.3, §System_Architecture.md):

```json
{
  "description": "string (≤ N chars, validated server-side)",
  "context": [{"type": "code|text", "content": "string"}],
  "notebookTitle": "string"
}
```

Response, success:

```json
{
  "code": "string",
  "model": "string",
  "tier": "wasm|backend|openai",
  "tokens": { "prompt": N, "completion": N },
  "requestId": "uuid"
}
```

Response, error (each tier and the aggregate failure use the same
shape):

```json
{
  "error": { "code": "string", "message": "user-facing string" },
  "tier": "backend|openai",
  "requestId": "uuid"
}
```

When the contract changes — dump the OpenAPI snapshot
(`.agents/skills/notebook-api/references/openapi-sync.md`).

## Streaming (LLM-NF-02)

If the endpoint streams, use **SSE** (`text/event-stream`) — not
WebSocket. Reasons:

- Already plays nice with HTTP/2 and the existing proxy
- Half-duplex matches the generate-then-stop pattern
- Reconnection is trivial via `Last-Event-ID`

Events: one per token batch (`event: token`), one terminal
(`event: done` with the full metadata blob), and `event: error`
on aborts. Client appends to the cell as events arrive; on
`error`, the partial code is **discarded**, not committed.

## Process

### 1. Read the source-of-truth docs

- `docs/requirements.md` §2.3, §3 — what must be supported
- `docs/qa/qa-plan.md` §6.6 — the scenarios any change must respect
- `docs/System_Architecture.md` — flow + endpoint shape
- `docs/execution-architecture.md` — generated code lands in the
  same QuickJS sandbox; no special privilege

### 2. Identify which tier(s) the change touches

| Tier | Lives in | Touched when |
|---|---|---|
| T1 (WASM) | `ui/src/**/llm/**` | Model loader, cache, warm-up, in-browser inference, T1→T2 fallback decision |
| T2 (backend proxy) | `api/app/modules/llm/**` | `/llm/generate`, provider abstraction, rate limit, prompt builder, T2→T3 fallback decision |
| T3 (OpenAI) | `api/app/modules/llm/providers/openai.py` (or similar) | Provider adapter, retry / timeout / error mapping |

Most changes touch exactly one tier. A "wire context from neighbour
cells" task touches T2 (prompt builder) **and** T1 (the WASM client
must pass the same context).

### 3. Plan the contract sync

LLM endpoints are part of the OpenAPI contract — when adding or
changing the endpoint shape, the standard contract-sync flow
applies (`scripts/openapi.py dump` → `pnpm api:generate` → facade
function in `@/shared/api/llm.ts`). See
`.agents/skills/notebook-api/references/openapi-sync.md`.

### 4. Plan the rate-limit + quota layer

Don't ship a new endpoint without rate limiting in the same PR.
The right pattern is a dependency-injected rate limiter on the
route — backed by the same store used for auth rate limits
(`api/docs/auth.md` §11 — `otp/request`, `otp/verify`, `refresh`
already have rate limits; reuse the mechanism).

### 5. Plan the metrics + logging

Per LLM-NF-04, every request is logged with: `model`, `tier`,
`prompt_tokens`, `completion_tokens`, `latency_ms`, `user_id`,
`request_id`, `error_code` (if any). **Not the prompt body.**
`structlog` JSON-friendly. Alert when daily OpenAI spend
> deploy threshold.

### 6. Plan the tests

Mandatory:

- **T2 unit**: prompt builder — given description + context,
  produces the expected wire prompt
- **T2 integration**: `/llm/generate` happy path + 429 + 502
  (provider down) + 504 (timeout) + per-tier fallback decision
- **T1 unit**: tier-decision function — given a request, the
  client picks WASM vs. network
- **T1 mock**: WASM-unavailable path (L-10)
- **Manual** browser walk — qa-plan §6.6 L-01..L-10 via
  manual-test-checklist

What to mock vs. real:

- **Never** call the real OpenAI API in CI. Use a recorded fixture
  (`vcrpy` or hand-rolled).
- **Never** load the real WASM model in unit tests; stub the
  client interface.
- Integration tests for T2 use `app.dependency_overrides` to swap
  the provider (per `notebook-api` §6).

### 7. Verify in the browser

`./start-services.sh`, then walk L-01..L-10 from
`manual-test-checklist.md` "LLM code generation". For UI changes
in the LLM flow, verify in Chrome (primary) + at least one of
Firefox/WebKit (cross-browser smoke per qa-plan §5.4) — WASM
behaves differently across engines.

## Red flags

- **OpenAI key in `VITE_*` env / client code / `.env.example` on
  the `ui` side** — leaked the moment it's deployed. Server-only.
- **Raw prompt text in a structured log line in `prod`** — privacy
  leak. Log token counts and metadata; never the body.
- **A new LLM endpoint without rate limiting** — abuse vector +
  cost explosion. Block until the limiter is wired.
- **Fallback to T3 on a T2 client error (4xx)** — wrong semantics.
  T3 fallback is for T2 unavailability (5xx, timeout), not for the
  user's malformed input.
- **Generated code auto-executed** — turns the model into an RCE
  in the user's browser. The Generate flow inserts code into a
  cell; the user runs it explicitly.
- **Direct call from frontend to `api.openai.com`** — the entire
  reason the proxy exists. Block at PR review.
- **WASM model bytes served from a CDN without integrity checking**
  — supply-chain risk. Pin a hash (`integrity` attribute, SRI)
  when fetching the model artefact.
- **Streaming endpoint that holds DB connections open for the
  duration of the stream** — connection-pool starvation. Acquire
  the connection only at request-bookkeeping time; the LLM call
  itself doesn't hold a DB connection.
- **No timeout on T2's call to T3** — a stuck OpenAI request stalls
  the worker forever. Per LLM-NF-01: 30 s hard cap, then 504.
- **Per-tier UX policy not stated in the PR** — silent fallback
  violates user expectations (qa-plan §10 risk). State which tier
  shows a badge / toast / nothing.
- **Mock that returns code on the unhappy path** — a test that
  asserts the cell was updated even when the request failed is
  asserting the opposite of the desired behaviour (L-04). Mental
  mutation test: would this test fail if the implementation were
  broken?

## Verification

Before marking an LLM-task done:

- [ ] `pytest` covers the T2 happy path, 429, 502/504, tier-fallback
      decision; tests do not call real OpenAI
- [ ] `pnpm test` covers the T1 tier decision and the WASM-
      unavailable path
- [ ] `ruff check .` clean (api); `pnpm lint`, `pnpm typecheck`
      clean (ui)
- [ ] OpenAPI snapshot regenerated if the contract changed
      (`scripts/openapi.py dump`) and `api/docs/openapi.json`
      committed
- [ ] If the ui consumes the new contract — `pnpm api:generate`
      run; facade function in `@/shared/api/llm.ts`; no direct
      `@/shared/api/generated/**` imports outside the facade
- [ ] Manual: walked L-01..L-10 in the local stack
      (`manual-test-checklist.md` "LLM code generation")
- [ ] DevTools Network: T1 happy path (L-01) sent **no** request
      to `/llm/generate`
- [ ] Rate limit in place; 21st call/minute returns 429 with
      `Retry-After`
- [ ] Logs in `prod` mode contain metadata only — no prompt body,
      no completion body, no API key (grep the container log)
- [ ] Generated code inserted, **not auto-executed**
- [ ] Build artefact (`pnpm build`) grepped for `sk-` /
      `ANTHROPIC` / provider key prefixes — clean
- [ ] qa-plan §6.6 scenarios mapped; new scenarios added to
      qa-plan in the same PR if introduced (`AGENTS.md` §9)
- [ ] Per-tier UX policy stated in the PR description
      (silent vs. badge vs. toast for each fall-through)
- [ ] No secrets in test fixtures, OpenAPI snapshot, or commit
      messages (`AGENTS.md` §11)

## Related

Primary (load alongside this skill):

- `docs/requirements.md` §2.3, §3 — functional + non-functional
- `docs/qa/qa-plan.md` §6.6 — L-NN scenarios
- `.agents/skills/notebook-api/SKILL.md` — backend side of the
  proxy
- `.agents/skills/notebook-ui/SKILL.md` — frontend side of the
  WASM tier

Secondary (load only when its sub-topic comes up):

- `.agents/skills/notebook-api/references/openapi-sync.md` —
  contract sync when the endpoint shape changes
- `docs/System_Architecture.md` §LLM proxy — HTTP flow
- `docs/execution-architecture.md` — why generated code in a cell
  is "safe enough" to insert without auto-running
- `.agents/skills/notebook-qa/references/manual-test-checklist.md`
  §"LLM code generation" — browser walk
- `AGENTS.md` §11 — mandatory secret-handling rules
