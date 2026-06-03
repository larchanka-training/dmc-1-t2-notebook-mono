# AI Architecture — JS Notebook code generation pipeline

> An architecture decision for the AI code-generation pipeline (Epic 07).
> Resolves the **Tech Lead — Design AI Generation Pipeline** task (issue #112).
>
> Source-of-truth order follows `AGENTS.md` §12.
> This document reconciles drift across `System_Architecture.md` §4.3, `requirements.md` §3, and `qa-plan.md` §6.6, and is forward-compatible with the design-v2 AI-UX (issue #74, UX Polish).

---

## 1. Overview

JS Notebook turns a plain-language prompt into runnable JavaScript/TypeScript — the project's headline feature (Epic 07).
This document designs the full generation pipeline: where the model runs, the prompt-cell schema, the AI Service API and its streaming contract, provider integration (AWS Bedrock + WebLLM), the validation/repair loop, and error handling.

The pipeline is **hybrid**: a request is served either by an in-browser model or by a backend proxy, and both paths return code in a unified shape so the UI does not depend on where generation happened.
This mirrors the hybrid model already used for code *execution* (`execution-architecture.md`) — same philosophy, a different workload.

This is a design document.
It **proposes** the `POST /api/v1/llm/generate` endpoint and its contract; the endpoint is implemented by the Epic 07 engineering tasks (notably #117 for validation), not by this document.

---

## 2. Execution strategy — where the AI runs

**Decision: a hybrid, three-tier pipeline with an explicit user choice in the MVP.**

| Tier | Where | UI label | Role |
|---|---|---|---|
| **T1** | In-browser (WebLLM on WebGPU) | **In-browser agent** | Local, no network, no API cost. Default for capable clients. |
| **T2** | Backend proxy → AWS Bedrock | **Cloud agent** | Server-side, hides keys, handles heavy/long prompts. |
| **T3** | Backend proxy → OpenAI | *(internal fallback)* | Last resort when T2 is unavailable (5xx/timeout). |

Order of preference is **T1 → T2 → T3**.
T1 and T2 are user-selectable in the MVP (two buttons, below); T3 is an internal backend fallback the user never picks directly.

> **Current sprint scope (MVP).**
> Generation is triggered by **two explicit buttons** — *In-browser agent* and *Cloud agent* (Meeting 4, 2026-06-03).
> There is **no silent auto-routing** yet: the user picks the path, which lets the team test and compare T1 vs T2 independently.
> A single "smart" button that auto-routes (e.g. by prompt size or client capability) and dynamic runtime memory profiling are **target/future** — collapsing the two buttons into one re-votes the Meeting 4 decision and is out of scope here.

Even with a manual choice, the *In-browser agent* button is **gated by client capability** (§3) so that a weak client cannot pick a path that freezes the tab.
This gating is **sprint scope**, not future.

The issue (#112) sketches a `< 200 chars → browser, else → backend` heuristic.
That heuristic is recorded as a **future** auto-routing input, not an MVP behaviour; the MVP routing decision is made by the user via the two buttons, constrained by capability gating.

### 2.1 Terminology — issue tools, canonical tiers, UI labels

The issue names the tools "AWS Bedrock" and "WebLLM"; the existing docs describe a "WASM → backend → OpenAI" chain; design v2 labels the buttons "In-browser" / "Cloud".
These are the same three tiers under different names:

| Issue #112 | `qa-plan.md` §6.6 | Design v2 UI | This doc |
|---|---|---|---|
| WebLLM (browser) | WASM LLM | In-browser agent | **T1** |
| AWS Bedrock (backend) | Backend LLM | Cloud agent | **T2** |
| OpenAI API | OpenAI API | *(internal)* | **T3** |

"WebLLM" is the concrete browser-inference library filling the same slot that `execution-architecture.md` calls "Frontend WASM".
"AWS Bedrock" is the managed gateway behind the backend proxy (§6), not a parallel chain.

---

## 3. Client capability detection

The MVP gives the user two buttons, but the *In-browser agent* button must not be a foot-gun.
WebLLM downloads a multi-hundred-MB model and runs inference on the client; on a weak machine that freezes the tab.
So the browser button is **gated** by a capability check before it is offered as enabled.
This gating is **sprint scope** — without it, two raw buttons ship a notebook that hangs on low-end clients.

Gating keeps the two-button model intact: the button is simply `disabled` with an explanatory tooltip when the client can't run WebLLM, and the user falls back to *Cloud agent*.

### 3.1 Signals (in priority order)

| # | Signal | Source | Rule |
|---|---|---|---|
| 1 | **WebGPU available** | `navigator.gpu` (+ `requestAdapter()`) | No WebGPU → browser button disabled. **Primary gate.** |
| 2 | **Device memory** | `navigator.deviceMemory` | `≤ 4 GB` → don't offer the browser button (coarse, Chromium-only, bucketed). |
| 3 | **Prompt length** | prompt char count | Long prompt → steer to *Cloud agent* (heavier local inference). |

**WebGPU is the primary signal, not WASM.**
WebLLM runs on **WebGPU**, not on plain WebAssembly.
Without a WebGPU adapter the in-browser tier cannot start regardless of how much RAM the client has.
This corrects `qa-plan.md` §6.6 **L-10** ("the browser does not support WASM"): the real gate is "no WebGPU", and the documented fallback (to the Cloud agent) is the right behaviour for that case.

`navigator.deviceMemory` is a coarse, bucketed hint (0.25..8 GB) available only on Chromium.
It is a secondary heuristic, never a hard guarantee.
Exact runtime probing via `measureUserAgentSpecificMemory()` (requires COOP/COEP isolation, async, Chromium-only) is **future** and not relied on for the MVP gate.

### 3.2 Graceful fallback on T1 failure

Capability detection is best-effort; it cannot predict every failure.
If the in-browser model fails to initialise, runs out of memory, or throws mid-generation, the path **falls back to the Cloud agent (T2)** rather than surfacing a raw error.
The fallback is shown to the user (a small notice), consistent with the per-tier UX policy in §8.

This makes the gate a *filter*, not a *promise*: it removes the obviously-incapable clients up front, and the runtime fallback covers the rest.

---

## 4. Prompt Cell schema and context

### 4.1 The Prompt Cell is the first-class `ai` cell

The design-v2 notebook (issue #74, UX Polish) introduces a first-class **`ai` cell** — it sits alongside `code` and `markdown` in the cell dispatcher.
This `ai` cell **is** the "Prompt Cell" the issue asks the Tech Lead to schematise.
It has three canonical **"Ask agent"** entry points:

| Entry point | Where | Surface |
|---|---|---|
| Empty-state primary button | A blank notebook | "Ask the agent" — the headline way to start a notebook |
| Insert-strip pill | Between any two cells | "Ask agent" pill next to Code / Text |
| Rendered `ai` cell | In the cell list | A prompt input + **In-browser** / **Cloud** buttons |

The `ai` cell carries a single user field — the prompt text — plus the chosen agent (`local` / `cloud`).
It is a transient authoring surface: it produces a code cell (§4.4) and is not itself an execution unit.

```jsonc
// ai (Prompt) cell
{
  "id": "cell-uuid",
  "type": "ai",
  "prompt": "group rows by quarter and chart it",
  "agent": "local"            // "local" (In-browser) | "cloud" (Cloud)
}
```

**MVP vs. design-v2 surface.**
Meeting 4 (2026-06-03) scoped the MVP to a simpler surface: a **markdown/text cell with two agent buttons**, where the prompt is the cell's own source text.
That is the *same* contract with a lighter UI — the request payload (§5) and the result lifecycle (§4.4) are identical whether the prompt comes from an `ai` cell or a text cell.
Which surface ships first is an **Epic 07 / UX-Polish front-end decision, not an architectural fork**; the schema and API below are built around the `ai` cell from the start so nothing breaks when it lands.
Persisting the `ai` cell type (IndexedDB, server sync) touches the **Epic 02** data model — flagged as a dependency, **not built by this document**.

### 4.2 Composing the request

Before calling any model, the prompt is combined with notebook context.
Context collection is **path-independent**: it runs the same way whether the model is the In-browser or the Cloud agent, so results are comparable (Meeting 4).

The assembled payload (wire shape in §5) carries:

- the user **prompt** (the Prompt Cell's text);
- an ordered **context** slice of neighbouring cells;
- the **notebook title** and target **language** (`javascript` | `typescript`).

### 4.3 Context collection rules

Context lets the model see what already exists in the notebook's global scope (variables, helpers) so generated code fits in.
Rules (from `ui/docs/tasks/07-llm-code-generation.md`):

- **Window:** the last **N = 10** cells above the Prompt Cell, in order.
- **Per-cell content:** `{ kind, source }` — cell type plus its text/code.
- **Size cap:** total context **≤ 8 KB**; if larger, **truncate from the oldest** cell until it fits (the nearest cells matter most).
- **Opt-out:** honour `notebookSettings.llm.includeContext` (default `true`); when `false`, send the prompt with no context.
- **Total request cap:** the whole request body is capped (§5); context is the first thing trimmed when over budget.

### 4.4 Result lifecycle — proposal, not auto-commit

Generation never silently mutates the notebook.
The result is inserted as a **separate new code cell below the Prompt Cell**, and that cell goes through a proposal lifecycle (design v2):

```
generating  →  proposal (new | edit)  →  accept | reject | regenerate
```

- **generating** — the code streams in (§5.3); a cursor shows progress.
- **proposal** — streaming done; the cell is a *draft* awaiting the user.
- **accept** — the draft becomes a normal code cell (still not executed — see §8).
- **reject** — a `new` draft is removed; an `edit` draft reverts to the original.
- **regenerate** — re-runs generation for a fresh draft.

This strengthens the security posture (§8): generated code is **neither auto-run nor auto-committed**.
The Meeting 4 MVP keeps the source Prompt Cell in place after generation, so the prompt stays as a re-runnable record.

### 4.5 System prompt and hard rules

The system prompt and non-negotiable generation rules live in a dedicated, version-controlled file (an `AGENTS.md`-style file for the generator, per Meeting 4) rather than being inlined in code.
The baseline format follows `requirements.md` §3.3:

```
System:
  You are an assistant that writes clean JavaScript/TypeScript code.
  Return ONLY the code — no explanations, no markdown fences.
  The code must run in a browser sandbox (QuickJS), with no Node or Python APIs.

User:
  Notebook context (optional):
  [last N=10 cells, ≤ 8 KB]

  Task:
  [Prompt Cell text]
```

The "return only code" instruction is a *request*, not a guarantee — the validation pipeline (§7) defensively strips any markdown the model adds anyway.

---

## 5. AI Service API

The backend exposes a single proxy endpoint for the **Cloud agent** (T2/T3).
The **In-browser agent** (T1) never calls it — it runs WebLLM locally and produces the same result shape in-process (§5.3).

```
POST /api/v1/llm/generate
```

Versioned under `/api/v1` to match the rest of the API.
This endpoint is **proposed here and implemented by Epic 07**; when it lands, the OpenAPI snapshot is regenerated (`scripts/openapi.py dump`) and `api/docs/openapi.json` is committed with it.

### 5.1 Request

```jsonc
{
  "prompt": "string",            // required; the Prompt Cell text, length-capped server-side
  "mode": "generate",            // "generate" (MVP) | "edit" (future, §5.4)
  "language": "javascript",      // "javascript" | "typescript"
  "notebookTitle": "string",     // optional, for prompt framing
  "context": [                     // optional; §4.3 rules, ≤ 8 KB, oldest-truncated
    { "kind": "code", "source": "const data = [...]" },
    { "kind": "markdown", "source": "# Data exploration" }
  ],
  "baseCode": "string"           // present only when mode == "edit": the code to improve
}
```

**Field reconciliation.**
The existing docs drift on names — `System_Architecture.md` §4.3 uses `description`, `07-llm-code-generation.md` uses `prompt`.
This document fixes **`prompt`** as canonical (it matches the design-v2 `ai` cell field and the front-end mock).
`System_Architecture.md` §4.3 is brought in line (Commit 8).

**The `mode` field is forward-compat (D9d).**
The MVP only sends `mode: "generate"`.
Design v2 also has an **agent-edit** action (improve existing code, return a diff); reserving `mode` now means adding `edit` later is **not** a breaking OpenAPI change.
See §5.4.

**Validation at the boundary.**
`prompt` is untrusted input: its length is enforced **server-side** (the client's own truncation is not trusted), with the `≤ 8 KB` prompt / `16 KB` total-request caps from `ui/docs/tasks/07-llm-code-generation.md`.
Over-limit → `422` (§8), never silently truncated mid-request.

### 5.2 Response (non-streaming shape)

Even though the transport streams (§5.3), the logical result and the terminal `done` event carry one shape:

```jsonc
// success
{
  "code": "const byQuarter = groupBy(data, 'q')\n...",
  "model": "amazon.nova-lite-v1",   // concrete model actually used
  "tier": "backend",                 // "wasm" | "backend" | "openai"
  "tokens": { "prompt": 312, "completion": 88 },
  "requestId": "uuid"
}
```

```jsonc
// error — same envelope at every tier and on aggregate failure
{
  "error": { "code": "rate_limited", "message": "user-facing string" },
  "tier": "backend",
  "requestId": "uuid"
}
```

`tier` tells the UI which path actually served the request — the hook for the per-tier UX policy (§8) and for surfacing a T2→T3 fallback.
`requestId` correlates with the structured backend logs (§8); it is safe to show the user for support.

### 5.3 Streaming — two distinct transports

Both agents stream code token-by-token so the user sees it "typed" rather than waiting on a blank screen (`requirements.md` LLM-NF-02).
**But the two buttons stream over completely different transports**, and the contract must say so or the front-end builds the wrong consumer:

| Agent | Tier | Transport | Mechanism |
|---|---|---|---|
| **Cloud agent** | T2 / T3 | **SSE over POST** (`text/event-stream`) | Server streams events; client reads the response body. |
| **In-browser agent** | T1 | **Local async stream** | WebLLM yields tokens in-process (async iterator); no HTTP, no SSE. |

**Cloud agent — SSE.**
The `POST /api/v1/llm/generate` response is `text/event-stream`.
SSE (not WebSocket) fits a half-duplex generate-then-stop flow, rides the existing proxy/HTTP-2, and reconnects via `Last-Event-ID`.
Event types:

```
event: token   data: {"delta": "const "}        # repeated, appended to the draft
event: done    data: {"model": ..., "tier": ..., "tokens": ..., "requestId": ...}
event: error   data: {"error": {"code": ..., "message": ...}, "tier": ..., "requestId": ...}
```

The client appends each `token.delta` to the draft code cell.
On `done` it stamps the metadata from §5.2.
On `error` the **partial code is discarded**, not committed — the draft does not survive a failed stream.

**In-browser agent — local stream.**
T1 has no network leg.
WebLLM is driven directly and yields token chunks via an async iterator; the same draft-append logic consumes them.
The "SSE contract" above is **backend-only** and does not apply here.

**Cancel / abort (both paths).**
Generation is cancellable.
For the Cloud agent the client calls `AbortController.abort()` on the fetch; for the In-browser agent it stops the WebLLM iteration.
On cancel the draft keeps the text accumulated so far and drops to an idle, user-editable state (it is **not** deleted) — matching the design-v2 proposal lifecycle (§4.4).

### 5.4 Edit mode (forward-compat, future)

Design v2 has a second action beyond "generate a new cell": **agent-edit** — improve an existing code cell and present the change as a **diff** (`proposalKind: "edit"`).
The contract anticipates it via `mode: "edit"` + `baseCode` (§5.1); the response `code` is the revised cell, surfaced as an `edit` proposal (§4.4) the user accepts or rejects.

Edit mode is **target/future** (ships with UX Polish, issue #74), not MVP.
Reserving the field now keeps the OpenAPI contract stable when it arrives.

---

## 6. Provider integration and fallback chain

### 6.1 AWS Bedrock is a model-agnostic gateway

The **Cloud agent** (T2) calls AWS Bedrock, a managed gateway to many foundation-model families (Amazon Nova / Titan, Meta Llama, Mistral, Anthropic, and others).
The backend is **model-agnostic**: the concrete model is selected by config, not hard-wired.
This is the "switch provider via config" capability `System_Architecture.md` §4.3 already anticipated.

**Model choice is budget-driven, and Claude is explicitly not the MVP pick.**
The model is whatever delivers acceptable code generation within the educational-project budget on a shared course account.
Candidates to weigh: **Amazon Nova Micro/Lite**, **Meta Llama**, **Mistral**.
The final pick is an open budget decision (§9).
This Tech Lead call **overrides** the "Anthropic Claude (priority)" wording in `System_Architecture.md` §4.3, which is corrected in the same change (Commit 8, per `AGENTS.md` §9/§12).

**Self-hosted backend model — rejected.**
Issue #112 floats "a local model on the backend" as a fallback tier.
Running a self-hosted LLM means GPU infrastructure, which is too expensive for this educational scope on a shared account (`AGENTS.md` production-quality / educational-scope rule).
The backend tier is a managed Bedrock call, not self-hosted inference.
This is a deliberate, documented trade-off.

### 6.2 The fallback chain

```
T1  In-browser agent (WebLLM / WebGPU)
      │  capability-gated (§3); on init failure / OOM / mid-gen throw →
      ▼
T2  Cloud agent — backend proxy → AWS Bedrock (budget model)
      │  on T2 upstream 5xx / timeout →
      ▼
T3  backend proxy → OpenAI API   (last resort)
```

Rules:

- **T1 → T2** is triggered by the user (button) or by capability gating / runtime failure (§3).
- **T2 → T3** triggers **only on T2 unavailability** — upstream `5xx` or timeout.
  It does **not** trigger on a `4xx` (e.g. `422` over-limit prompt, `429` rate limit): a bad request is the user's input problem, and retrying it against a more expensive provider just burns money (`AGENTS.md` §11 cost-control intent; see §8).
- **T3** is internal — the user never selects "OpenAI"; they selected *Cloud agent*, and T3 is its fallback.

### 6.3 Mapping to qa-plan §6.6 scenarios

Every `L-NN` scenario from `qa-plan.md` §6.6 maps onto this chain:

| Scenario | Behaviour in this architecture |
|---|---|
| **L-01** WASM succeeds | T1 serves it; no network request (verifiable in DevTools). |
| **L-02** WASM can't → backend | T1 falls back to T2; user gets code. |
| **L-03** backend fails → OpenAI | T2 `5xx`/timeout → T3; fallback surfaced (§8). |
| **L-04** all tiers fail | Clear error; editor untouched; button re-enabled (§8). |
| **L-05** empty prompt | Button disabled / inline validation; no request (§4.1, §8). |
| **L-06** prompt too long | Server-side `422`; client shows a counter; no fall-through (§5.1, §8). |
| **L-07** insert position | **Superseded by Meeting 4** — see note below. |
| **L-08** tab closed mid-gen | Partial result not saved; abort cleans up (§5.3). |
| **L-09** WASM not yet loaded | Loading indicator; request queued until the model is warm. |
| **L-10** no WASM | Re-read as **no WebGPU** (§3.1); auto-fallback to the Cloud agent. |

> **L-07 conflict.**
> `qa-plan.md` §6.6 L-07 expects generated code "inserted at the current cursor position".
> Meeting 4 (2026-06-03) decided the result is a **separate new code cell below the Prompt Cell** (§4.4).
> Meeting 4 is the newer decision and wins; **L-07 is superseded**.
> Updating the qa-plan scenario is a follow-up task, outside this doc-only change.

---

## 7. Validation and repair

A model returns prose, markdown fences, or broken syntax as readily as clean code.
The validation pipeline turns a raw completion into something safe to insert, and re-prompts when it can't.
This is the design for the Epic 07 backend task **#117**.

### 7.1 Pipeline

```
raw completion
  → 1. extract code     (strip markdown fences / surrounding prose)
  → 2. guard emptiness  (empty / whitespace-only → no cell)
  → 3. syntax check     (parse/build without executing)
  → 4a. valid  → insert as a proposal (§4.4)
  → 4b. invalid → retry: re-prompt with the error, bounded attempts
```

**1. Extract code.**
Despite the "return only code" system instruction (§4.5), defensively strip ```` ```js ````/```` ``` ```` fences and any leading/trailing explanation.
Prefer the first fenced block when present; otherwise take the whole trimmed body.

**2. Guard emptiness.**
If extraction yields empty or whitespace-only text, **no cell is inserted** and the user sees "No code generated" (§8).
An empty answer is a generation failure, not a valid result.

**3. Syntax check — without executing.**
The code is parsed/built to catch syntax errors **without running it**.
Untrusted generated code is never executed during validation; it only ever runs later, explicitly, inside the QuickJS sandbox (`execution-architecture.md`).

**4. Retry.**
On a syntax failure (or an empty answer), the service **re-prompts the model with the error information** appended — "the previous output failed with `<error>`, return corrected code" (#117).
Retries are **bounded** (a small fixed cap); after the cap the pipeline gives up and returns a user-facing error (§8) rather than looping or burning budget.

### 7.2 Per-path validation (the duplication)

The **same logical pipeline** runs on whichever path generated the code, but the tools differ — and this duplication is unavoidable, since the In-browser agent has no backend to lean on.

| Step | Cloud agent (T2/T3) | In-browser agent (T1) |
|---|---|---|
| Extract code | Backend (Python) | Browser (JS) |
| Syntax check | **esbuild via Python subprocess** (no execution) | **esbuild-wasm** or a QuickJS parse pass, in the browser |
| Retry | Re-prompt Bedrock/OpenAI | Re-prompt WebLLM |
| Injection pre-filter (§8) | **Yes** (backend) | **Absent** — documented trade-off |

`esbuild` is the chosen syntax/build checker (#117): on the backend it is invoked as a console subprocess from Python; the In-browser path duplicates the check with `esbuild-wasm` (or a QuickJS parse) so a locally-generated cell is held to the same bar.

The prompt-injection pre-filter (§8) lives only on the backend.
The In-browser path has no server-side filter — a deliberate MVP trade-off: T1 keeps the user's prompt fully local (a privacy win) at the cost of no server-side injection screening.
The risk is bounded because generated code is never auto-run and only ever executes in the sandbox.

---

## 8. Security and error handling

### 8.1 Secrets and keys

- **Provider keys are server-side only.**
  Bedrock/OpenAI credentials live in the backend environment and are **never** sent to the client, never embedded in the front-end bundle, never logged (`requirements.md` LLM-NF-05, `AGENTS.md` §11).
  The whole reason the Cloud agent is a *proxy* is to keep keys off the client.
- **No provider key in a `VITE_*` var.**
  Anything `VITE_`-prefixed ends up in the shipped JS — effectively published.
  The In-browser agent uses WebLLM (open weights, no key); it needs no provider secret.
- **Production credentials via AWS Secrets Manager.**
  Local/dev settings may sit in local files; prod/cloud credentials are sourced from **AWS Secrets Manager** (Meeting 4), not baked into images or env files in the repo.

### 8.2 Untrusted input and output

- **Prompts are untrusted input.**
  Validate at the backend boundary: length cap (§5.1 → `422`), basic shape.
  Don't trust client-side truncation.
- **Prompt-injection pre-filter (backend).**
  Before the main model call, the Cloud path screens the prompt (a cheap classifier pass) for injection patterns; "ignore previous instructions"–style content is treated as prompt *content*, not as instructions.
  This is backend-only (§7.2).
- **Generated code is untrusted output.**
  It is inserted as a **proposal**, **never auto-run** and **never auto-committed** (§4.4).
  Execution only ever happens later, explicitly, in the QuickJS sandbox (`execution-architecture.md`) — the defence-in-depth boundary.

### 8.3 Rate limiting and cost control

- **Rate limit (LLM-NF-03):** ≤ **20 requests/min/user** on `/api/v1/llm/generate`; over-limit → `429` with a `Retry-After` header.
  Reuses the auth rate-limit mechanism (`api/docs/auth.md`).
- **T3 quota / cost ceiling:** OpenAI (T3) costs real money.
  Apply a per-user daily quota **and** a per-deployment global ceiling, with an alert on threshold breach (`AGENTS.md` §11 cost-control intent).
  The In-browser agent (T1) also self-throttles to avoid burning client CPU on rapid clicks.

### 8.4 Error model

Errors follow the same split as `execution-architecture.md` §9: **transport errors** use HTTP status codes; a completed generation that simply failed validation is reported in-band.
The UI keys off `error.code` + `tier`, not off message text.

| Condition | Code | User-facing behaviour |
|---|---|---|
| Over rate limit | `429` + `Retry-After` | "Limit reached · try again in 1 min"; button re-enables after the window. |
| Prompt too long | `422` | Inline counter + error; request not sent (§5.1). |
| Empty prompt | — | Button disabled / inline validation; no request (L-05). |
| Timeout > 30 s | `504` | Hard cap (LLM-NF-01); abort + "Generation timed out · retry". |
| Connection drop mid-stream | — | Partial code discarded (§5.3); "Generation failed · retry". |
| Safety filter blocked | in-band | "Request was blocked by a safety filter" — friendly, not raw. |
| All tiers failed (L-04) | in-band | Clear error; editor untouched; button re-enabled. |
| No code generated | in-band | "No code generated"; no cell inserted (§7.1). |

**Principles** (mirroring `execution-architecture.md` §9.3):

- **Safe messages** — no server paths, model versions, or stack internals leak to the user.
- **Editor integrity** — a failed generation never mutates existing cells; a discarded draft leaves no trace.
- **Per-tier UX policy** — the fall-through is **not silent**: a T1→T2 or T2→T3 switch shows a small notice (qa-plan §10 flags silent fallback as an expectation violation).
  `tier` in the response (§5.2) drives this.

### 8.5 Logging (LLM-NF-04)

Every request is logged structurally (`structlog`) with **metadata only**: `model`, `tier`, `prompt_tokens`, `completion_tokens`, `latency_ms`, `user_id`, `request_id`, `error_code`.
**Never** the raw prompt or completion body in `prod` — they may contain PII or the user's proprietary code (`AGENTS.md` §11).
Dev mode may log bodies behind an explicit flag.
Provider keys never appear in any log line, at any level.

---

## 9. Open questions

Decisions deliberately left open for the team / upcoming sprints:

- **Exact Bedrock budget model (TBD).**
  The Cloud agent is model-agnostic (§6.1); the concrete pick (Nova Micro/Lite vs Llama vs Mistral) is a budget+quality call still to be made.
- **Chat assistant vs. prompt cell.**
  Whether a full chat assistant that can manage several cells is needed, or the `ai`/prompt-cell UX is enough for now (Meeting 4 — research/future).
- **Non-code answers.**
  How to handle prompts that ask for prose rather than code — likely a new text cell.
  Output validation currently targets code only (Meeting 4).
- **Structured output from the browser model.**
  Whether WebLLM reliably supports structured/tool output to distinguish a code answer from a text answer.
- **Resource-heaviness signal.**
  How precisely to detect a resource-heavy request and when to force it to the backend (beyond the §3 capability gate) — ties into the future single-smart-button routing.
- **Multi-step generation.**
  Whether to split generation and validation across two models (one generates, one checks).
- **Environment wiring for context collection.**
  Where the context-collection settings best live.

---

## 10. Related documents

| Document | Relation |
|---|---|
| `requirements.md` §2.3, §3 | LLM functional/non-functional requirements; prompt format |
| `System_Architecture.md` §3.3, §4.3 | LLM Client + LLM Proxy; contract reconciled here (Commit 8) |
| `execution-architecture.md` §9 | Error-model split this doc mirrors; the sandbox generated code runs in |
| `qa-plan.md` §6.6 | `L-01..L-10` scenarios mapped in §6.3 |
| `ui/docs/tasks/07-llm-code-generation.md` | Front-end Epic 07 flow, context rules, SSE consumer |
| issue #117 | Backend validation & repair task (§7) |
| issue #74 (design v2) | UX Polish design — `ai` cell, agent-edit, proposal lifecycle (§4, §5.4) |
