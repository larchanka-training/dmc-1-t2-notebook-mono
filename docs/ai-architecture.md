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
