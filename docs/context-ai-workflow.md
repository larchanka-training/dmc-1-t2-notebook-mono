# AI Context Workflow (Epic 07 / #116)

How the notebook **AI generation context** is built, shaped, persisted and fed
to the model. This is the operational companion to
[`ai-architecture.md`](ai-architecture.md) §4.3 — that document is the contract;
this one walks the end-to-end flow across the front-end (`ui`) and backend
(`api`).

> **TL;DR.** The front-end **Context Builder** turns the notebook's cells into a
> compact `{ kind, source }[]` slice (previous cells + a globals digest +
> truncated outputs). Two modes, switched by a flag: **at-send** builds it lazily
> at generate time; **persisted** keeps it server-side, in sync, incrementally.
> When the context outgrows the budget, a **pluggable summary strategy** rolls
> the oldest history into one `summary` item.

---

## 1. What the context is

Generation needs to know what already exists in the notebook so the produced
code fits in (reuses variables, matches data shapes). The context is an ordered
(old → new) list of items, each `{ kind, source }`:

| `kind` | Source | Notes |
|---|---|---|
| `code` / `markdown` / `text` | the verbatim cell source | one item per previous cell |
| `output` | a **truncated** digest of a cell's outputs | real result shapes; capped per cell |
| `globals` | a compact **name/type/shape** digest of declared globals | one item; static analysis (acorn) of code cells |
| `summary` | the budget-aware roll-up of older history | added only when a roll-up happens (§5) |

**Budgets** (mirrored on both sides, the backend re-validates and returns `422`
on an oversized request):

- context slice ≤ **`LLM_MAX_PROMPT_BYTES`** (8 KiB) UTF-8;
- ≤ **10** items (the generation endpoint's `context` cap);
- whole request body ≤ 16 KiB.

When over budget, the **oldest** cells are trimmed first (the nearest cells matter
most).

---

## 2. The flag — two modes

`VITE_AI_CONTEXT_MODE` (front-end build-time env, default `at-send`):

| Mode | When the context is formed | Persisted? |
|---|---|---|
| **`at-send`** (default) | built from the cells **at the moment the user generates** | no |
| **`persisted`** | built **asynchronously**, kept in sync, **stored server-side** | yes |

Both modes send the same wire payload to the model — `{ prompt, context }` — so
generation does not depend on which mode produced the context.

---

## 3. Context generation / formation (the Context Builder)

Front-end, `ui/src/features/notebook/model/context-ai/`:

- `contextBuilder.ts` — `buildNotebookContext(cells, opts)` assembles the
  `{ kind, source }[]` slice: a `globals` digest first, then the previous cells
  (windowed to the newest *N* = 10) with their verbatim source and a truncated
  `output` digest, then byte- and item-capped (oldest dropped first).
- `globalsDigest.ts` — static analysis (acorn) of code cells → a compact
  `globals: name: type; …` line. MVP reports *declared* globals (not live runtime
  values); runtime introspection is a future enhancement.
- `aiContextMode.ts` — the `aiContextModeAtom` flag (from `VITE_AI_CONTEXT_MODE`).
- `aiContext.ts` — Mode B orchestration (§4.2).

The "initial call" that *uses* the context stays in `model/codeGenerator.ts`
(the generate action) — it prepends the assembled context to the prompt.

---

## 4. The two flows

### 4.1 Mode A — `at-send` (default)

```
user clicks generate
  → buildNotebookContext(cells, { beforeCellId })   // cells above the prompt cell
  → prepend the context block to the prompt
  → run the model (in-browser / cloud)
```

Stateless, no backend round-trip, nothing persisted.

### 4.2 Mode B — `persisted`

Wired at boot (`ui/src/app/model/setup.ts`) behind the flag:
`startAiContextSync(notebookId)`.

```
on entry:    GET /notebooks/{id}/ai-context  → persistedContextAtom
             seed the per-cell working model from the current cells
             (NO PUT — the loaded server state is not overwritten on entry)

on edit/add: recompute ONLY the changed cells' contributions (incremental),
             debounced → one PUT /notebooks/{id}/ai-context per burst

on delete:   clear the stored context, reseed from scratch → DELETE + PUT

on generate: flush the pending persist, then send the LOCAL working model,
             cell-aware (cells above the prompt cell) with live outputs
```

Key properties:

- **The local working model drives generation; the backend is a remote
  store/sync.** Generation always reads the local per-cell cache — cell-aware
  (only cells **above** the prompt cell, §4.3) and with **live** outputs. The
  loaded server context is *not* used to build the prompt and is *not*
  overwritten by an immediate rebuild on entry.
- **Incremental, not from scratch.** Each cell's contribution (source item +
  declared globals — **not** outputs) is cached (`contributionsAtom`); a user
  action recomputes only the cells it touched. Only the **first** seed and a
  **delete** reseed everything.
- **Debounced persist.** A burst of edits coalesces into **one** PUT (like
  autosave, ~400 ms) instead of one-per-keystroke; the send path flushes the
  pending persist first. Persists run through a single serialized queue, in
  user-operation order.
- **Outputs are read live, never cached.** A cell run does not bump the notebook
  revision, so a cached output digest would go stale. The cache holds
  source+globals; the stored PUT carries source+globals; generation appends a
  fresh output digest read from the cell at send time.
- **Resilient.** A failed persist (backend down) is **caught + logged** in the
  queue — it never stalls the queue nor surfaces as an unhandled rejection. A
  failed entry `GET` is logged + flagged; generation reads the local working
  model regardless, so it still gets current context when the backend is down.

---

## 5. Persistence + summary strategies (backend)

Backend, `api/app/modules/ai_context/`:

- `GET/PUT/DELETE /api/v1/notebooks/{id}/ai-context` — owner-scoped (404 when the
  notebook is missing/deleted, 403 when not owned). Stored in
  `notebooks.notebook_ai_context` (`context` JSONB, `summary` TEXT,
  `history_count`, `updated_at`).
- On `PUT`, the **summary service** rolls the submitted context up to the
  generation budget (≤ 8 KiB / ≤ 10 items): it keeps the newest cells verbatim
  and folds the oldest prefix into a single `summary` item. The PUT body itself
  is bounded by `LLM_MAX_PROMPT_BYTES` (422 when over).

### 5.1 Strategies — `LLM_CONTEXT_SUMMARY_STRATEGY`

The roll-up algorithm is pluggable and selected by an env var; the call sites
don't change.

| Strategy id | What it does | Cost / risk |
|---|---|---|
| `compact-oldest` (**default**) | deterministic, model-free fold of the oldest cells into a one-line digest | none — no network, no token cost, no injection surface |
| `llm` | summarise the folded cells with **Bedrock** for a higher-quality digest | token cost + latency on the `PUT`; notebook content is sent to the model (the summariser's system prompt frames it strictly as data); **falls back to the deterministic digest on any provider failure**, so persistence never breaks |

Both strategies share the same keep-newest / fold-oldest shape
(`summary.py:_roll_up`); they differ only in how the folded prefix becomes the
summary string.

---

## 6. Environment / settings

| Variable | Side | Default | Purpose |
|---|---|---|---|
| `VITE_AI_CONTEXT_MODE` | ui | `at-send` | `at-send` \| `persisted` (§2) |
| `LLM_CONTEXT_SUMMARY_STRATEGY` | api | `compact-oldest` | `compact-oldest` \| `llm` (§5.1) |
| `LLM_MAX_PROMPT_BYTES` | api | `8192` | the generation context byte budget; also the stored-history PUT cap |

There is no separate stored-history byte knob — it is `LLM_MAX_PROMPT_BYTES`.
The item count is bounded by the 10-item generation cap (the roll-up enforces it).

---

## 7. File map

| Area | Path |
|---|---|
| Context Builder + globals digest | `ui/src/features/notebook/model/context-ai/{contextBuilder,globalsDigest}.ts` |
| Mode flag | `ui/src/features/notebook/model/context-ai/aiContextMode.ts` |
| Mode B orchestration (load / incremental sync / queue / send-assembly) | `ui/src/features/notebook/model/context-ai/aiContext.ts` |
| Generate action (the consumer) | `ui/src/features/notebook/model/codeGenerator.ts` |
| Boot wiring (Mode B) | `ui/src/app/model/setup.ts` |
| HTTP facade | `ui/src/shared/api/aiContext.ts` |
| Backend module (model / repo / service / controller) | `api/app/modules/ai_context/` |
| Summary strategies | `api/app/modules/ai_context/services/summary.py` |
| Migration | `api/liquibase/changelog/changes/ai_context/` |

---

## 8. Related documents

| Document | Relation |
|---|---|
| [`ai-architecture.md`](ai-architecture.md) §4.3 / §5 | the contract this workflow implements (context rules, request shape, modes, summary) |
| [`execution-architecture.md`](execution-architecture.md) §9 | the output/error model the `output` context kind digests |
| issue #116 | the Context Builder task |
