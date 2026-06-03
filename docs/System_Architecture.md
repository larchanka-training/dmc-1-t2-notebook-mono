# System Architecture — JavaScript Notebook Platform

> A web application for interactive work with code and notes, an analog of Jupyter Notebook for JavaScript/TypeScript, with support for synchronization, offline mode, and code generation via LLM.

---

## 1. General Concept

The platform consists of two main parts: the **frontend** (an SPA application in the browser) and the **backend** (REST/WebSocket API + database). It can operate fully offline thanks to the local IndexedDB storage. Synchronization with the server is triggered manually by the user.

---

## 2. High-Level Diagram

```
┌─────────────────────────────────────────────────────────────┐
│                        FRONTEND (SPA)                        │
│                                                             │
│  ┌──────────────┐   ┌──────────────┐   ┌────────────────┐  │
│  │  Notebook UI  │   │  JS Runtime  │   │  LLM Client    │  │
│  │  (Editor +   │   │  (QuickJS /  │   │  (API proxy    │  │
│  │   Renderer)  │   │   Temporal)  │   │   via backend) │  │
│  └──────┬───────┘   └──────┬───────┘   └───────┬────────┘  │
│         │                  │                    │           │
│  ┌──────▼──────────────────▼────────────────────▼────────┐  │
│  │                  State Manager (Zustand / Redux)       │  │
│  └──────────────────────────┬─────────────────────────────┘  │
│                             │                               │
│  ┌──────────────────────────▼─────────────────────────────┐  │
│  │              IndexedDB  (local storage)                │  │
│  └──────────────────────────┬─────────────────────────────┘  │
│                             │  (manual synchronization)     │
└─────────────────────────────┼───────────────────────────────┘
                              │ HTTPS / WebSocket
┌─────────────────────────────▼───────────────────────────────┐
│                         BACKEND (Python 3.12)               │
│                                                             │
│  ┌──────────────┐   ┌──────────────┐   ┌────────────────┐  │
│  │  Auth Service │   │  Notebooks   │   │  LLM Proxy     │  │
│  │  (JWT/OAuth) │   │  API         │   │  Service       │  │
│  └──────┬───────┘   └──────┬───────┘   └───────┬────────┘  │
│         │                  │                    │           │
│  ┌──────▼──────────────────▼────────────────────▼────────┐  │
│  │                     Database (PostgreSQL)              │  │
│  └────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
                              │
              ┌───────────────▼──────────────┐
              │   External LLM API           │
              │   (OpenAI / Anthropic / etc.) │
              └──────────────────────────────┘
```

---

## 3. Frontend Components

### 3.1 Notebook UI

| Subcomponent | Description |
|---|---|
| `NotebookView` | Notebook container, list of cells |
| `CodeCell` | Cell with a code editor (Monaco Editor) |
| `TextCell` | Cell with Markdown text (viewing and editing) |
| `CellToolbar` | Buttons: Run, Delete, Move Up/Down, Generate via LLM |
| `OutputPanel` | Output of code execution results (text, charts, tables) |
| `NotebookList` | List of all the user's notebooks |

**Code editor:** Monaco Editor (the same one used in VS Code) — support for JS/TS syntax, autocompletion, themes.

### 3.2 JS Runtime

Running JavaScript code **directly in the browser** without sending it to the server.

**Runtime options:**
- **QuickJS (via WebAssembly)** — an isolated execution environment, a secure sandbox
- **iframe sandbox** — a simple option, code runs in an isolated iframe
- **Web Workers** — execution in a separate thread, does not block the UI

**Recommendation:** QuickJS via WASM — maximum isolation, support for modern JS, the ability to emulate TypeScript (strip types).

> **Hybrid execution.** Frontend QuickJS/WASM is the primary path, but when the client's RAM is ≤ 4 GB or for a resource-intensive request, execution is routed to the backend (the server-side QuickJS sandbox). The full model, routing, and flow diagram are in [`execution-architecture.md`](./execution-architecture.md).

**Output support:**
- `console.log` → text output
- Returned data (arrays, objects) → automatic visualization (tables)
- Integration with Chart.js / D3.js → charts and diagrams

### 3.3 LLM Client

The client does not access the LLM provider directly — all requests go through the **backend proxy** (for security: the API key is stored only on the server).

**Usage scenario:**
1. The user writes a text cell describing the task
2. Clicks the "Generate code" button
3. The frontend sends the context (description + neighboring cells) to the backend
4. The backend builds a prompt and queries the LLM
5. The LLM returns code → a new `CodeCell` is created below

### 3.4 State Manager

Manages the application state (list of notebooks, cells, execution results, synchronization status).

**Recommendation:** Zustand — lightweight, suitable for this type of application.

### 3.5 Local Storage (IndexedDB)

All data is stored locally to enable offline operation.

**Storage structure:**

```
IndexedDB: js-notebook (version 1)
└── notebooks   keyPath: id, index: updatedAt
                value = NotebookJSON {
                  formatVersion, id, title, createdAt, updatedAt,
                  cells: [ { id, kind, content, updatedAt } ]
                }
```

A notebook is a single record; its cells are stored inline in the
`NotebookJSON` value (see §5), not in a separate `cells` store. Run outputs and
execution counts are not persisted — they are ephemeral run products,
reproduced by re-running. There is no `sync_queue` store yet; server
synchronization is a future layer (§4.2, §7).

**Library:** `idb` — a minimal Promise-based wrapper over IndexedDB with TypeScript support.

---

## 4. Backend Components

### 4.1 Auth Service

| Function | Details |
|---|---|
| Registration / login | Email + password, optionally OAuth (Google, GitHub) |
| Tokens | JWT Access Token (15 min) + Refresh Token (30 days) |
| Session storage | Refresh tokens in the DB, with the ability to invalidate them |

### 4.2 Notebooks API

REST API for synchronizing notebooks.

```
POST   /api/notebooks          — create a notebook
GET    /api/notebooks          — list the user's notebooks
GET    /api/notebooks/:id      — get a notebook with its cells
PUT    /api/notebooks/:id      — update / synchronize
DELETE /api/notebooks/:id      — delete

POST   /api/notebooks/:id/sync — manual synchronization (merge local changes)
```

**Synchronization strategy:** Last-Write-Wins by `updatedAt` at the cell level. In case of a conflict, the user is shown a diff for manual resolution.

### 4.3 LLM Proxy Service

An intermediary service that hides the API key from the client.

> The AI generation pipeline (execution strategy, Prompt Cell schema, full
> request/response contract, streaming, providers, validation, error handling)
> is specified in [`ai-architecture.md`](./ai-architecture.md) — the source of
> truth for this feature. The summary below is kept consistent with it.

```
POST /api/v1/llm/generate
Body: {
  prompt: string,          // the Prompt Cell text
  mode: string,            // "generate" (MVP) | "edit" (future)
  language: string,        // "javascript" | "typescript"
  notebookTitle: string,   // optional
  context: Cell[]          // neighboring cells, ≤ 8 KB, oldest-truncated
}
Response: {
  code: string,            // generated code
  model: string,           // concrete model used
  tier: string,            // "wasm" | "backend" | "openai"
  tokens: { prompt: number, completion: number },
  requestId: string
}
```

The backend path streams the response via **SSE** (`text/event-stream`); the
in-browser path (WebLLM) produces the same shape locally.

**Providers:** the backend is **model-agnostic** — a budget-driven model via
**AWS Bedrock** (config-switchable), with **OpenAI** as the last-resort
fallback. The concrete Bedrock model is a budget decision (see
`ai-architecture.md` §6, §9).

### 4.4 Database (PostgreSQL)

```sql
-- Users
users (id, email, password_hash, created_at)

-- Notebooks
notebooks (id, user_id, title, created_at, updated_at)

-- Cells
cells (id, notebook_id, type ENUM('code','text'), content TEXT,
       cell_order INT, created_at, updated_at)

-- Execution results (optional, only the latest run)
cell_outputs (cell_id, output TEXT, executed_at)
```

---

## 5. Notebook Storage Format

A notebook is serialized as a JSON document. This is the shape the frontend
stores locally in IndexedDB (§3.5) and that the future sync layer will exchange
with the backend; it is aligned field-for-field with the backend contract
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
      "content": "const x = Array.from({length: 100}, (_, i) => i / 10);\nconst y = x.map(Math.sin);\nplot(x, y);",
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
- run outputs and execution counts are **not** persisted — they are ephemeral
  run products, reproduced by re-running.

---

## 6. Technology Stack

| Layer | Technology | Rationale |
|---|---|---|
| Frontend Framework | React + TypeScript | Component model, ecosystem |
| Code editor | Monaco Editor | Full-fledged IDE experience, JS/TS support |
| JS Runtime | QuickJS (WASM) | Isolation, security, modern JS |
| State Management | Zustand | Simplicity, performance |
| Local storage | `idb` (IndexedDB) | Offline mode |
| Visualization | Chart.js / Observable Plot | Charts directly from cells |
| Backend Framework | Python 3.12 | Performance, TypeScript |
| ORM | Prisma | Type safety, migrations |
| Database | PostgreSQL | Reliability, JSONB for cells |
| Authentication | JWT + bcrypt | Standard for SaaS |
| LLM | Anthropic Claude API | Code generation quality |
| Deployment | Docker + Docker Compose | Environment reproducibility |

---

## 7. Data Flows

### Creating and executing a cell (offline)
```
User → NotebookUI (add a cell)
  → StateManager (update state)
  → IndexedDB (save locally)
  → QuickJS Runtime (execute code)
  → OutputPanel (display result)
  → IndexedDB (save output)
```

### Code generation via LLM
```
User ("Cloud agent" button)
  → LLM Client (collect context)
  → Backend /api/v1/llm/generate
  → LLM Proxy → AWS Bedrock (budget model) → OpenAI (fallback)
  → SSE stream: code
  → New code cell below, inserted as a proposal (accept / reject)
  → IndexedDB (save)
```

> The In-browser agent (WebLLM) serves the same flow locally, with no backend
> call. See [`ai-architecture.md`](./ai-architecture.md) for the full pipeline.

### Manual synchronization
```
User ("Sync" button)
  → Sync Manager (reads IndexedDB + sync_queue)
  → Backend /api/notebooks/:id/sync
  → Merge on the server
  → Response: current state
  → Update IndexedDB + StateManager
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
