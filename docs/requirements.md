# Requirements: JavaScript Notebook — LLM Integration

## 1. Project Overview

**JavaScript Notebook** is a web application in the style of Jupyter Notebook for writing and executing JavaScript code directly in the browser, with support for text blocks, synchronization through a backend, and code generation using an LLM.

---

## 2. System Architecture

### 2.1 General Diagram

```
┌─────────────────────────────────────────────────────┐
│                    FRONTEND (SPA)                   │
│                                                     │
│  ┌──────────────┐   ┌──────────────┐               │
│  │  Notebook UI │   │  JS Runtime  │               │
│  │  (React/Vue) │   │  (QuickJS /  │               │
│  │              │   │   Sandboxed  │               │
│  │  - Code Cell │   │   iframe)    │               │
│  │  - Text Cell │   └──────────────┘               │
│  │  - Output    │                                  │
│  └──────────────┘   ┌──────────────┐               │
│                     │  IndexedDB   │               │
│                     │  (offline)   │               │
│                     └──────────────┘               │
└──────────────────────────┬──────────────────────────┘
                           │ REST / WebSocket
┌──────────────────────────▼──────────────────────────┐
│                    BACKEND (Python)                │
│                                                     │
│  ┌──────────────┐   ┌──────────────┐               │
│  │  Auth Service│   │  Sync Service│               │
│  │  (JWT)       │   │  (Notebooks) │               │
│  └──────────────┘   └──────────────┘               │
│                                                     │
│  ┌──────────────┐   ┌──────────────┐               │
│  │  LLM Proxy   │   │  DB          │               │
│  │  (Anthropic/ │   │  (PostgreSQL │               │
│  │   OpenAI API)│   │   / SQLite)  │               │
│  └──────────────┘   └──────────────┘               │
└─────────────────────────────────────────────────────┘
```

> **Code execution is hybrid.** The JS Runtime in the browser (QuickJS/WASM) is the primary path; when the client's RAM is ≤ 4 GB or for a resource-intensive request, execution is routed to the backend. The model, routing, and flow diagram are in [`execution-architecture.md`](./execution-architecture.md).

### 2.2 Data Storage

| Layer       | Technology       | Purpose                                     |
|-------------|------------------|---------------------------------------------|
| Frontend    | IndexedDB        | Offline storage of all notebooks            |
| Backend     | PostgreSQL/SQLite | Synchronized copies of notebooks           |
| Format      | JSON             | Notebook structure (see section 4)          |

### 2.3 Where Does the LLM Live?

**LLM requests are proxied through the backend.**

Reasons:
- The API key must not be visible on the client
- Ability to log and rate-limit requests
- Centralized model replacement without a frontend deploy

Call diagram:
```
Frontend → POST /api/llm/generate → Backend → Anthropic/OpenAI API → Backend → Frontend
```

---

## 3. LLM Integration Requirements

### 3.1 Functional Requirements

| ID     | Requirement                                                                                      |
|--------|--------------------------------------------------------------------------------------------------|
| LLM-01 | The user creates a text block with a task description and clicks the **Generate Code** button   |
| LLM-02 | The system sends the contents of the text block to the backend                                  |
| LLM-03 | The backend builds a prompt and calls the LLM API                                                |
| LLM-04 | The LLM returns code, which is inserted into a new or existing code block below the text block   |
| LLM-05 | The user can edit the generated code before executing it                                        |
| LLM-06 | Generation is triggered only explicitly (by a button), not automatically                         |
| LLM-07 | Context is supported: neighboring notebook blocks can optionally be included in the prompt       |

### 3.2 Non-Functional Requirements

| ID     | Requirement                                                                                         |
|--------|-----------------------------------------------------------------------------------------------------|
| LLM-NF-01 | The LLM response time must not exceed 30 seconds; if exceeded, a timeout with an error message |
| LLM-NF-02 | **Target/future:** streaming of the response to display code as it is generated. Preferred transport is SSE for the Cloud agent; the current MVP uses a regular JSON REST response |
| LLM-NF-03 | Rate limiting: no more than 20 LLM requests per minute per user                                |
| LLM-NF-04 | Logging of all LLM requests on the backend: model, token counts, latency, tier, request id, user id, error code. In `prod` log prompt **metadata** only (length / hash), never the raw prompt or completion body — they may contain PII or proprietary user code (`AGENTS.md` §11). Dev mode may log bodies behind a flag |
| LLM-NF-05 | The API key is stored only on the server (env variable) and is never sent to the client        |

### 3.3 Prompt Format

```
System:
  You are an assistant that writes clean JavaScript code.
  Return ONLY the code, with no explanations or markdown blocks.
  The code must work in a browser sandbox environment without a Python API.

User:
  Notebook context (optional):
  [previous blocks]

  Task:
  [contents of the user's text block]
```

---

## 4. Notebook Data Structure (JSON)

```json
{
  "id": "uuid-v4",
  "title": "Notebook title",
  "createdAt": "ISO-8601",
  "updatedAt": "ISO-8601",
  "cells": [
    {
      "id": "cell-uuid",
      "type": "text",
      "content": "Task description in markdown"
    },
    {
      "id": "cell-uuid",
      "type": "code",
      "language": "javascript",
      "content": "console.log('hello')",
      "output": {
        "type": "text",
        "value": "hello",
        "executedAt": "ISO-8601"
      },
      "generatedByLLM": true
    }
  ]
}
```

---

## 5. Tests

### 5.1 Unit Tests (Frontend)

| ID     | Component      | Scenario                                                       | Expected result                              |
|--------|----------------|----------------------------------------------------------------|----------------------------------------------|
| UT-F-01 | Cell Store    | Adding a code block                                            | The block appears in the cells list          |
| UT-F-02 | Cell Store    | Deleting a block                                               | The block disappears, the order is preserved |
| UT-F-03 | Cell Store    | Moving a block (drag & drop)                                   | The cells order is updated correctly         |
| UT-F-04 | JS Runtime    | Executing `2 + 2`                                              | Output: `4`                                  |
| UT-F-05 | JS Runtime    | Executing code with a syntax error                             | Output: an error message, without a UI crash |
| UT-F-06 | JS Runtime    | Executing `console.log('test')`                                | Output: `test`                               |
| UT-F-07 | LLM Client    | Successful request — response with code                        | The code is inserted into a new code block   |
| UT-F-08 | LLM Client    | Request timeout (> 30s)                                        | An error is shown, the block is not created  |
| UT-F-09 | Serializer    | Serializing a notebook into JSON                               | The JSON matches the schema (section 4)      |
| UT-F-10 | Serializer    | Deserializing valid JSON                                       | All blocks are restored                      |
| UT-F-11 | IndexedDB     | Saving and reading a notebook offline                          | The data is identical before and after       |

### 5.2 Unit Tests (Backend)

| ID     | Service         | Scenario                                                      | Expected result                              |
|--------|-----------------|---------------------------------------------------------------|----------------------------------------------|
| UT-B-01 | Auth           | Registration with valid data                                  | A user is created, a JWT is returned         |
| UT-B-02 | Auth           | Login with an incorrect password                              | 401 Unauthorized                             |
| UT-B-03 | Auth           | Request with an expired JWT                                   | 401, the token is rejected                   |
| UT-B-04 | Sync           | Saving a notebook (POST /api/notebooks)                       | 201, the notebook is in the DB               |
| UT-B-05 | Sync           | Getting the list of a user's notebooks                        | Only this user's notebooks                   |
| UT-B-06 | Sync           | Updating a notebook with a stale `updatedAt`                  | 409 Conflict                                 |
| UT-B-07 | LLM Proxy      | Successful forwarding of a request to the LLM API             | The generated code is returned               |
| UT-B-08 | LLM Proxy      | The LLM API is unavailable                                    | 502 Bad Gateway, an error message            |
| UT-B-09 | LLM Proxy      | Rate limit exceeded (> 20 req/min)                            | 429 Too Many Requests                        |
| UT-B-10 | LLM Proxy      | The API key is missing from env                               | 500, the server does not start / logs an error |

### 5.3 Integration Tests

| ID     | Scenario                                                                                      | Expected result                                                  |
|--------|-----------------------------------------------------------------------------------------------|------------------------------------------------------------------|
| IT-01  | The user registers → logs in → creates a notebook → synchronizes                             | The notebook is saved in the DB and in IndexedDB               |
| IT-02  | The user creates a text block with a description → clicks Generate → receives a code block   | A code block with code appears below the text block            |
| IT-03  | The user works offline → creates a notebook → goes online → synchronizes manually            | The data is saved and synchronized without loss                |
| IT-04  | Two users synchronize different notebooks at the same time                                    | No conflicts between the notebooks of different users          |
| IT-05  | Executing code with an infinite loop                                                          | The runtime is interrupted by a timeout (5s), the UI does not freeze |

### 5.4 E2E Tests (Playwright / Cypress)

| ID     | Scenario                                                                                  |
|--------|-------------------------------------------------------------------------------------------|
| E2E-01 | Open the app → create a notebook → write JS code → execute → see the result              |
| E2E-02 | Create a text block → generate code via the LLM → run the code → see the result          |
| E2E-03 | Register → create a notebook → synchronize → log out → log in → the notebook is still there |
| E2E-04 | Disable the internet (DevTools) → create a notebook → enable the internet → synchronize   |

---

## 6. Additional Features (Optional)

- **TypeScript support** — ignoring types (as in Bun), executing TS as JS
- **Notebook export** — download as a `.json` or `.js` file
- **Shared notebooks** — public links to a notebook (read-only)
- **Dark/light theme** — a toggle
- **Markdown rendering** — text blocks are rendered as Markdown
- **Hotkeys** — `Ctrl+Enter` to execute, `Shift+Enter` to create a block

---

## 7. Technology Stack (Recommended)

| Part         | Technology                        |
|--------------|-----------------------------------|
| Frontend     | React + TypeScript                |
| State        | Zustand / Redux Toolkit           |
| JS Runtime   | QuickJS (WASM) / sandboxed iframe |
| Offline DB   | IndexedDB (via idb)               |
| Editor       | CodeMirror 6                      |
| Backend      | Python                            |
| Auth         | JWT + bcrypt                      |
| Database     | PostgreSQL (or SQLite for the MVP) |
| LLM          | Anthropic Claude / OpenAI         |
| Tests FE     | Vitest + React Testing Library    |
| Tests BE     | Jest / Vitest                     |
| E2E          | Playwright                        |
