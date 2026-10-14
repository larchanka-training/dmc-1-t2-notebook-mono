# System Architecture — JavaScript Notebook Platform

> A web application for interactive work with code and notes, an analog of Jupyter Notebook for JavaScript/TypeScript, with support for synchronization, offline mode, and code generation via LLM.

---

## 1. General Concept

The React application edits and executes notebook cells in the browser. It
saves notebooks locally in IndexedDB and, while signed in, pushes changes to
the server in the background (autosync,
larchanka-training/js-notebook#134); there is no manual sync button.

This overview describes the monorepo's pinned API/UI sources. Future execution,
device-storage and AI UX features are marked separately; production sign-off
is tracked in the [migration plan](./aeza-migration-implementation-plan.md#5-phase-g-operational-sign-off).

---

## 2. High-Level Diagram

```text
Browser: React + CodeMirror 6 + Reatom
  ├─ Cell execution → Web Worker → QuickJS/WASM
  ├─ Rich output → sandboxed HTML iframe / image renderer
  ├─ Local inference → WebLLM/WebGPU
  └─ IndexedDB v4 (notebooks, sync, meta, local outputs)
          │ HTTPS / JSON REST (background notebook sync, Cloud AI)
          ▼
Aeza VPS: nginx → FastAPI
  ├─ Email OTP / JWT sessions → Resend (email delivery)
  ├─ Notebooks + AI context → SQLAlchemy → PostgreSQL 16
  └─ Cloud LLM proxy → OpenRouter (server-side credentials)
```

Backend cell-execution routing and WebSocket collaboration are future paths,
not part of the current browser execution / REST synchronization flow.

---

## 3. Frontend Components

### 3.1 Notebook UI

| Subcomponent | Description |
|---|---|
| `NotebookView` | Notebook container, list of cells |
| `CodeCell` | Cell with the CodeMirror 6 editor |
| `TextCell` | Cell with Markdown text (viewing and editing) |
| `CellToolbar` | Buttons: Run, Delete, Move Up/Down, Generate via LLM |
| `OutputPanel` | Output of code execution results (text, charts, tables) |
| `NotebookList` | List of all the user's notebooks |

**Code editor:** CodeMirror 6, with JavaScript language support, autocompletion
and theme extensions (`ui/src/features/notebook/ui/CodeEditor.tsx`).
The table names describe UI responsibilities rather than exact exported component names.

### 3.2 JS Runtime

Cell JavaScript runs in **QuickJS/WASM inside a Web Worker**. The browser path
is implemented; routing low-memory or resource-heavy runs to a backend worker
is a **target/future** extension. See [execution architecture](./execution-architecture.md).

`console.log` and the trailing expression produce output. `display()` supports
HTML and images; chart libraries such as Chart.js/Observable Plot are not
bundled UI dependencies. HTML scripts run in a separate sandboxed iframe with
CSP, outside QuickJS: notebook Stop and timeout may not stop them. See
`ui/src/features/notebook/ui/OutputFrame.tsx` for the enforced policy and warning.
COOP/COEP headers enable cross-origin isolation / SharedArrayBuffer; they do
not prove the safety of every generated program or HTML output.

### 3.3 LLM Client

The user explicitly chooses **In-browser agent** (WebLLM/WebGPU) or **Cloud
agent** (backend proxy → OpenRouter). Local inference needs no provider key;
model assets must first be downloaded. Cloud credentials stay on the server.

The toolbar sends the text cell prompt and notebook context, then inserts a
new code or markdown cell below it. The inserted cell is editable and saved
through the normal notebook lifecycle; generated code is **not auto-run**.
An explicit proposal/accept/reject lifecycle remains a UX target. T1 uses the
Context Builder; T2 currently sends source-only context. See
[AI architecture](./ai-architecture.md) for per-surface limits and validation.

### 3.4 State Manager

Manages the application state (list of notebooks, cells, execution results, synchronization status).

**Implementation:** Reatom atoms/actions, including explicit async context handling.

### 3.5 Local Storage (IndexedDB)

All data is stored locally to enable offline operation, and the background
autosync layer (larchanka-training/js-notebook#134) pushes it to the server
once the user is signed in (§4.2, §7).

**Storage structure:**

```
IndexedDB: js-notebook (version 4)
├── notebooks   keyPath: id, index: updatedAt
│               value = NotebookJSON {
│                 formatVersion, id, title, createdAt, updatedAt,
│                 cells: [ { id, kind, content, updatedAt } ]
│               }
├── sync        keyPath: notebookId (per-notebook sync state)
│               value = { notebookId, remoteCreated, dirty, deletedCells[],
│                         lastSyncedUpdatedAt, ownerId }
├── meta        key-value (e.g. seed-tombstone:<ownerId>)
└── outputs     keyPath: notebookId (bounded local-only output overlay)
```

A notebook is a single record in `notebooks`; its cells are stored inline in the
`NotebookJSON` value (see §5), not in a separate `cells` store. Selected rich
outputs (`result`, `html`, `image`) persist in the separate, bounded `outputs`
overlay; they never join notebook autosync. Console streams, runtime errors
and execution counts are not persisted as notebook content. The `sync` partition
holds the autosync queue
(dirty flag, `deletedCells` tombstones, last-synced marker, owner) and the
`meta` partition holds durable markers such as the per-account seed tombstone.

**Multi-user on one device.** There is one IndexedDB (`js-notebook`) per browser
origin — it is **not** partitioned per user, so notebooks of every account that
signed in on the device physically coexist in it. Separation between accounts is
**logical**, via owner attribution, not storage isolation:

- The boot seed (welcome) notebook id is per-user —
  `resolveDemoNotebookId() = uuidv5(DEMO_NAMESPACE, user.id)` — so two accounts
  never collide on the floor notebook (the legacy shared id is migrated on boot).
- Every other notebook is attributed by an `ownerId` (`user.id`) recorded in its
  `sync` partition when a dirty change is made while signed in.
- Boot opens the **newest notebook owned by the current user**; a notebook with
  no provable owner is skipped, so a shared device never opens another account's
  local notebook, and an **owner-gate** refuses to auto-push a queue whose
  `ownerId` differs from the current user (no cross-account upload).

**Current limitation and planned device policy.** Sign-out pauses sync but does
not wipe local notebooks; records remain reachable through DevTools. The active
backend is still IndexedDB. [larchanka-training/js-notebook#136](https://github.com/larchanka-training/js-notebook/issues/136)
defines a future **untrusted/in-memory default** for new sessions, **trusted
persistence by explicit opt-in**, and a separate trusted-device “sign out and
erase” action. Ordinary trusted logout preserves local data.

Acceptance for that implementation must protect unsynchronized changes: before
untrusted logout discards the in-memory working copy, attempt a bounded final
sync; if changes remain unsaved, warn and obtain an explicit discard/cancel
choice before clearing them. Network failure must not block logout indefinitely. Cleanup must cover legacy disk records,
queues/tombstones, metadata, local outputs, in-flight writes and other tabs;
clearing only the active memory adapter is insufficient. Anonymous-data
import/keep/discard and migration of existing records need separate decisions.
See `ui/docs/architecture/remote-sync.md` and `ui/docs/auth.md` for current behavior.

**Library:** `idb` — a minimal Promise-based wrapper over IndexedDB with TypeScript support.

---

## 4. Backend Components

### 4.1 Auth Service

| Function | Details |
|---|---|
| Registration / login | Passwordless email + one-time code (OTP); no password, no third-party OAuth |
| Tokens | JWT Access Token (`HS256`) + Refresh Token with rotation |
| Session storage | Refresh tokens / sessions in the DB, with the ability to invalidate them (logout revokes immediately) |

### 4.2 Notebooks API

REST API for synchronizing notebooks.

```
POST   /api/v1/notebooks          — create a notebook (client may supply the id)
GET    /api/v1/notebooks          — list the user's notebooks
GET    /api/v1/notebooks/:id      — get a notebook with its cells
PATCH  /api/v1/notebooks/:id      — update / synchronize (send the whole notebook)
DELETE /api/v1/notebooks/:id      — soft-delete (marked deleted, not erased)
```

There is no dedicated `/sync` endpoint: synchronization reuses these CRUD endpoints (`PATCH` carries the full notebook plus `deletedCells` tombstones).

**Notebook count cap (client-side).** The backend enforces no maximum number of notebooks per user. `GET /api/v1/notebooks` is paginated and its `limit` is capped at `200` (page size, `le=200`); the frontend reads only that single first page. A notebook created beyond it would be invisible in the sidebar and never synced, so the UI caps creation at the page size (`MAX_NOTEBOOKS = LIST_PAGE_LIMIT = 200`), reusing the same slot count as the "keep at least one notebook" delete guard. The welcome seed counts as one slot (it is restorable), leaving 199 user-created notebooks. The "+" button is disabled with an explanatory tooltip at the cap and re-enables when any notebook is deleted. This is an active-list limit per account, not an IndexedDB limit: local storage is shared across accounts on a device and holds more rows. Frontend detail: `ui/docs/architecture/remote-sync.md`.

**Synchronization strategy:** Last-Write-Wins by `updatedAt` at the cell level, merged on the server; if timestamps tie, the server version wins. There is no manual diff resolution.

### 4.3 LLM Proxy Service

An intermediary service that hides the API key from the client.

> The AI generation pipeline (execution strategy, Prompt Cell schema, full
> request/response contract, target streaming, providers, validation, error handling)
> is specified in [`ai-architecture.md`](./ai-architecture.md) — the source of
> truth for this feature. The summary below is kept consistent with it.

```
POST /api/v1/llm/generate
Body: {
  prompt: string,          // the Prompt Cell text
  mode: string,            // "generate" | "edit" (backend accepts; UI future)
  language: string,        // "javascript" | "typescript"
  notebookTitle: string,   // optional
  context: Cell[]          // ≤ 10 items / 8 KiB UTF-8 source bytes; server rejects overflow
}
Response: {
  resultKind: string,      // "code" | "text"
  content: string,         // generated code, or prose when resultKind == "text"
  model: string,           // concrete model used
  tier: string,            // "backend" for this endpoint
  tokens: { prompt: number, completion: number },
  requestId: string
}
```

The backend returns **JSON** (`application/json`), not SSE. Local WebLLM has a
separate in-process stream/result handled by the UI bridge. Cloud streaming is
a future contract; it is not used by the current controller.

**Providers:** the backend is **model-agnostic** — OpenRouter is the active production cloud adapter (`LLM_PROVIDER=openrouter`, [`larchanka-training/js-notebook#186`](https://github.com/larchanka-training/js-notebook/issues/186)), with the legacy AWS Bedrock adapter deprecated. T2 failure is terminal in the MVP; an external-provider fallback is a far-future option (see `ai-architecture.md` §6.2, §9).

### 4.4 Database (PostgreSQL)

SQLAlchemy models and the full Liquibase chain define these application tables:

| Schema | Tables / storage |
|---|---|
| `users` | `users`, `otps`, `sessions`, `refresh_tokens`, `llm_entitlement`, `llm_usage_counter`, `llm_usage_event`, `llm_usage_reservation` |
| `notebooks` | `notebooks` (metadata, `owner_id`, `cells` JSONB, soft-delete timestamp), `notebook_ai_context` |

`app.notebooks` and `app.users` are historical baseline names. Later migrations
move them into `notebooks` and `users`; there are no separate application
`cells` or `cell_outputs` tables. Rich output overlays are local-only (§3.5).
Liquibase's `databasechangelog` / `databasechangeloglock` bookkeeping in `public`
is separate from the application schemas.

Sources: [master changelog](../api/liquibase/changelog/changelog-master.xml),
[notebook schema move](../api/liquibase/changelog/changes/notebooks/0003-move-notebooks-schema.xml),
[LLM usage tables](../api/liquibase/changelog/changes/users/0007-llm-usage-controls.xml),
[Notebook ORM](../api/app/modules/notebooks/models/notebook.py).
This is a repository inventory, not a fresh production database inspection.

---

## 5. Notebook Storage Format

A notebook is serialized as a JSON document. This is the shape the frontend
stores locally in IndexedDB (§3.5) and that the background autosync layer (§4.2,
§7) exchanges with the backend; it is aligned field-for-field with the backend contract
(`api/docs/openapi.json`).

```json
{
  "formatVersion": 1,
  "id": "f47ac10b-58cc-4372-a567-0e02b2c3d479",
  "title": "My Notebook",
  "createdAt": 1735689600000,
  "updatedAt": 1735776000000,
  "cells": [
    {
      "id": "9b2e4c1a-7d3f-4a2b-8c1e-2d4f6a8b0c1e",
      "kind": "markdown",
      "content": "## Task description\nLet's build a sine chart...",
      "updatedAt": 1735776000000
    },
    {
      "id": "3f1d8e7b-5a2c-4e9d-b6f1-0a3c5e7d9b1f",
      "kind": "code",
      "content": "const x = Array.from({length: 100}, (_, i) => i / 10);\nconst y = x.map(Math.sin);\nconsole.log(y);",
      "updatedAt": 1735776000000
    }
  ]
}
```

**Field notes:**

- `formatVersion` — persistent format version (currently `1`). A breaking
  format change bumps it; older stored documents are migrated forward on read.
- `createdAt` / `updatedAt` — Unix epoch **milliseconds** (number), not ISO
  strings. Present on the notebook and on every cell.
- cell `kind` — `"code"` (JavaScript source) or `"markdown"` (GFM text).
- cell order is the array order; there is no separate `order` field.
- outputs and execution counts are absent from this notebook/sync format.
  Selected rich outputs persist separately in the local-only overlay (§3.5).

---

## 6. Technology Stack

| Layer | Technology | Role |
|---|---|---|
| Frontend | React 19 + TypeScript + Vite | Application and build |
| Editor / state | CodeMirror 6 / Reatom | Code editing and reactive state |
| Cell runtime | QuickJS/WASM in Web Worker | Isolated cell execution |
| Local storage | `idb`, IndexedDB v4 | Notebooks, sync metadata, local output overlays |
| Output | Application renderers + sandboxed HTML iframe | Text/results, HTML and images |
| Backend | Python + FastAPI | Versioned `/api/v1` JSON API |
| ORM / migrations | SQLAlchemy 2.0 / Liquibase | Models and schema evolution |
| Database | PostgreSQL 16 | Accounts, notebooks and AI context/usage |
| Authentication | Email OTP via Resend + JWT / rotating refresh tokens | Passwordless sign-in |
| AI | WebLLM locally; OpenRouter through the backend | Explicit local/cloud choice |
| Deployment | Docker Compose on Aeza, nginx, GHCR | Single production host; immutable image tags |

At the pinned API commit `3711e96`, the Docker runtime is **Python 3.14**,
API CI uses **3.12**, and `pyproject.toml` declares **>=3.12** compatibility.
These are different scopes. Packaging/CI alignment is tracked in
[mono #259](https://github.com/larchanka-training/dmc-1-t2-notebook-mono/issues/259);
an unmerged API branch is not the monorepo runtime baseline.

---

## 7. Data Flows

### Creating and executing a cell (offline)
```
User → NotebookUI (add a cell)
  → StateManager (update state)
  → IndexedDB (save locally)
  → QuickJS Runtime (execute code)
  → OutputPanel (display result)
  → IndexedDB outputs store (selected rich outputs, local-only)
```

### Code generation via LLM
```
User ("Cloud agent" button)
  → LLM Client (collect context)
  → Backend /api/v1/llm/generate
  → LLM Proxy → OpenRouter (budget model; legacy Bedrock deprecated)
  → JSON result: resultKind + content
  → New ordinary code or markdown cell below, enter edit; no auto-run
  → IndexedDB (save)
```

> The In-browser agent (WebLLM) serves the same flow locally, with no backend
> call. See [`ai-architecture.md`](./ai-architecture.md) for the full pipeline.

### Background synchronization (autosync)
```
Local autosave commits (no user action)
  → Remote autosync engine (larchanka-training/js-notebook#134) reads IndexedDB + deletedCells tombstones
  → Backend PATCH /api/v1/notebooks/:id (full notebook + deletedCells)
  → Merge on the server (Last-Write-Wins by cell updatedAt)
  → Response: current state
  → Update IndexedDB + StateManager
  → A status indicator reflects syncing / synced / offline / error
```

---

## 8. Ideas for Additional Features

- **Notebook export** — to a `.js` file, an HTML page, or PDF
- **Notebook templates** — starter sets of cells for common tasks
- **Collaboration** — collaborative editing via WebSocket (CRDT / Yjs)
- **Versioning** — notebook change history (git-like)
- **npm packages in cells** — loading libraries via esm.sh / skypack directly in the runtime
- **Variables across cells** — a shared execution context (as in Jupyter)
- **Keyboard shortcuts** — Shift+Enter (run), Ctrl+B (new cell), etc.
- **Themes** — light/dark, several color schemes
- **Built-in AI chat** — questions about the code directly in the notebook interface
