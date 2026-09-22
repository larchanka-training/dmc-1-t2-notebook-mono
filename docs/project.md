# JS Notebook — Project Documentation

## Project Overview

**JS Notebook** is a Jupyter Notebook-style web application adapted for JavaScript. Users can create interactive notebooks with code blocks (JavaScript) and text blocks, run code directly in the browser, and sync their notebooks with the server through a personal account.

The project is inspired by [Jupyter Notebook](https://jupyter.org/), but it targets the JS ecosystem, features a modern interface, and supports AI code generation.

---

## Project Goals

- Provide a convenient environment for interactively writing and running JavaScript code
- Support offline work via local storage (IndexedDB / localStorage)
- Enable notebook synchronization with a cloud backend (SaaS model)
- Integrate an LLM for generating code from a text description

## Active Development Roadmap (September 2026)

Production was cut over from Beget to Aeza and functionally accepted on
2026-09-13. The current priority is completing post-cutover automation,
observation, backups, and retirement before the Beget service period ends on
2026-09-18. The remaining gates are maintained in
[`aeza-migration-implementation-plan.md`](./aeza-migration-implementation-plan.md).

| Target | Milestone | Status |
|---|---|---|
| 2026-09-10 | Manual immutable GitHub Actions deployment to Aeza staging | Done; staging retired |
| 2026-09-13 | Production database and Cloudflare cutover to Aeza | Done; functional smoke passed |
| 2026-09-14 | Automatic/manual Aeza production deployment | Done; PR #233 merged, deploy verified |
| 2026-09-14+ | Automated off-host backups and scheduled restore verification | In progress; tooling in PR #237, operational activation pending |
| 2026-09-14+ | Pinned OpenRouter guard plus application usage quotas | Pending |
| 2026-09-18 | Beget workflow retirement, credential removal, and service cancellation | In progress; workflow archived in `archive/beget-workflows/` |

Production now runs on Aeza under the isolated `jsnotes-production` Compose
project. `deploy-aeza-production.yml` is the sole active production workflow;
legacy Beget and staging deployment paths are retired (`deploy-beget.yml` is
archived in `archive/beget-workflows/`). OpenRouter access remains restricted to
two accounts until pinned models, application-side quotas, and usage accounting
are fully rolled out.

---

## Functional Requirements

### Notebooks

| Feature | Description |
|---|---|
| Create a notebook | The user can create a new notebook |
| Notebook list | View and manage existing notebooks |
| Delete / rename | Basic CRUD operations on notebooks |

### Blocks (Python / Cells)

| Block type | Description |
|---|---|
| **Code block** | A block with JavaScript code; supports execution and output display |
| **Text block** | A Markdown or plain-text block for descriptions and notes |

For each block, the following are available:
- Editing the content
- Running (for code blocks)
- Moving up / down
- Deleting

### Code Execution

- JavaScript code runs **in the browser** (QuickJS/WASM in a Web Worker)
- Hybrid model: when the client's RAM is ≤ 4 GB or for a resource-intensive request, execution moves to the backend — see [`execution-architecture.md`](./execution-architecture.md)
- Output (`console.log`, charts, errors) is displayed directly below the block
- TypeScript is supported optionally: types are ignored at execution time (similar to Bun)

### Data Storage

- **Locally**: notebooks are saved in the browser's `IndexedDB` — fully offline operation
- **Format**: a JSON notebook structure (an array of blocks with a type, content, and metadata)
- **Cloud synchronization**: automatic background autosync for signed-in users (no manual button), requires authorization

### Accounts and Synchronization

- Registration and sign-in (email + password or OAuth)
- Notebooks are pushed to the server **automatically in the background** after each local autosave
- Conflict resolution: the strategy is defined in the technical specification

### LLM — Code Generation

- The user adds a text block with a description of the desired code
- Clicks the **"Generate code"** button
- The LLM returns a ready-made code block, which is inserted right after the text block
- The user can edit and run the generated code

---

## System Architecture

```
┌─────────────────────────────────────────────────────┐
│                    FRONTEND (SPA)                   │
│                                                     │
│  ┌──────────────┐   ┌──────────────────────────┐   │
│  │  UI / Editor │   │   JS Runtime (iframe /   │   │
│  │  (React/Vue) │   │      Web Worker)         │   │
│  └──────┬───────┘   └──────────────────────────┘   │
│         │                                           │
│  ┌──────▼───────────────────────────────────────┐  │
│  │           IndexedDB (offline storage)        │  │
│  └──────────────────────────────────────────────┘  │
└────────────────────────┬────────────────────────────┘
                         │ REST API / WebSocket
┌────────────────────────▼────────────────────────────┐
│                    BACKEND                          │
│                                                     │
│  ┌──────────────┐   ┌───────────────────────────┐  │
│  │  Auth Service│   │   Notebooks API           │  │
│  │  (JWT/OAuth) │   │   (CRUD + Sync)           │  │
│  └──────────────┘   └───────────────────────────┘  │
│                                                     │
│  ┌──────────────────────────────────────────────┐  │
│  │        LLM Proxy (→ OpenAI / Anthropic)      │  │
│  └──────────────────────────────────────────────┘  │
│                                                     │
│  ┌──────────────────────────────────────────────┐  │
│  │           Database (PostgreSQL / SQLite)      │  │
│  └──────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────┘
```

### Why the LLM Runs on the Backend

- API keys must not be accessible on the client
- The backend acts as an **LLM proxy**: it receives a request from the frontend, adds the system prompt and the key, and returns the result
- Enables caching, rate limiting, and request logging

---

## Technology Stack (Proposed)

### Frontend
- **React** + TypeScript
- **CodeMirror** or **Monaco Editor** — a code editor with syntax highlighting
- **IndexedDB** (via `idb` or `Dexie.js`) — offline storage
- **iframe / Web Worker** — an isolated runtime for executing JS

### Backend
- **Python 3.12**
- **PostgreSQL** — storage for notebooks, accounts, and synchronization history
- **JWT** — authorization
- **LLM Proxy** — requests to the OpenAI / Anthropic API

---

## Notebook Storage Format (JSON)

```json
{
  "id": "uuid",
  "title": "My Notebook",
  "createdAt": "2025-01-01T00:00:00Z",
  "updatedAt": "2025-01-15T12:00:00Z",
  "cells": [
    {
      "id": "cell-1",
      "type": "text",
      "content": "## Description\nThis notebook demonstrates building a chart."
    },
    {
      "id": "cell-2",
      "type": "code",
      "language": "javascript",
      "content": "const data = [1, 2, 3, 4, 5];\nconsole.log(data);"
    }
  ]
}
```

---

## Ideas for Additional Features

- **Export**: saving a notebook as a `.js` file or PDF
- **Templates**: starter notebooks for common tasks
- **Sharing**: a public link to a notebook (read-only)
- **Version history**: rolling back to a previous version of a notebook
- **Collaboration**: real-time collaborative editing
- **NPM packages**: the ability to import external libraries via a CDN (for example, `d3`, `lodash`)
- **Dark/Light theme**: switching the interface theme
- **Keyboard shortcuts**: Shift+Enter to run a block, similar to Jupyter

---

## Still To Be Clarified

- A detailed technical specification for synchronization (the conflict resolution strategy)
- The specific LLM provider and the system prompt for code generation
- The data retention policy and GDPR
- The deployment strategy (Docker, cloud, self-hosted)
