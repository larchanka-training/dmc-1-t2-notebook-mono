# JS Notebook — Project Documentation

## Project Overview

**JS Notebook** is a Jupyter Notebook-style web application adapted for JavaScript. Users can create interactive notebooks with code blocks (JavaScript) and text blocks, run code directly in the browser, and sync their notebooks with the server through a personal account.

The project is inspired by [Jupyter Notebook](https://jupyter.org/), but it targets the JS ecosystem, features a modern interface, and supports AI code generation.

---

## Project Goals

- Provide a convenient environment for interactively writing and running JavaScript code
- Support offline work via local storage (IndexedDB)
- Enable notebook synchronization with a cloud backend (SaaS model)
- Integrate an LLM for generating code from a text description

## Active Development Roadmap (September–October 2026)

Production was cut over from Beget to Aeza and functionally accepted on
2026-09-13. Post-cutover deployment milestones, rollback drills, and health
probes are documented in [`aeza-production-observation-report.md`](./aeza-production-observation-report.md).
Beget VPS decommissioning completed on 2026-09-22, while continuous production
observation, backup restore verification, and pinned guard models remain pending operational gates in the migration plan.
The remaining gates are maintained in
[`aeza-migration-implementation-plan.md`](./aeza-migration-implementation-plan.md).

| Target | Milestone | Status |
|---|---|---|
| 2026-09-10 | Manual immutable GitHub Actions deployment to Aeza staging | Done; staging retired |
| 2026-09-13 | Production database and Cloudflare cutover to Aeza | Done; functional smoke passed |
| 2026-09-14 | Automatic/manual Aeza production deployment | Done; larchanka-training/dmc-1-t2-notebook-mono#233 merged, deploy verified |
| 2026-09-14 | Automated off-host backup tooling and disposable restore verification script | Done; backup and disposable restore verification tooling merged in larchanka-training/dmc-1-t2-notebook-mono#237 |
| 2026-09-14+ | Pinned OpenRouter guard plus application usage quotas | In progress (partial); Step 8e usage controls merged (larchanka-training/dmc-1-t2-notebook-api#99, larchanka-training/dmc-1-t2-notebook-api#100, larchanka-training/dmc-1-t2-notebook-api#101, larchanka-training/dmc-1-t2-notebook-api#102; larchanka-training/dmc-1-t2-notebook-ui#152; larchanka-training/dmc-1-t2-notebook-mono#238, larchanka-training/dmc-1-t2-notebook-mono#239, larchanka-training/dmc-1-t2-notebook-mono#240, larchanka-training/dmc-1-t2-notebook-mono#241); pinned guard verification pending under the `aeza-migration-implementation-plan.md` §5 operational sign-off gate "A pinned guard model has passed repeated checks" (related roadmap context in larchanka-training/js-notebook#185) |
| 2026-09-18 | Beget workflow retirement, credential removal, and service cancellation | Done; larchanka-training/dmc-1-t2-notebook-mono#243 merged, secrets removed, Beget VPS decommissioned on 2026-09-22, tracking issue larchanka-training/js-notebook#187 closed |
| 2026-09-22 | Legacy AWS preview workflows audit and Bedrock deprecation | Done; 9 workflows archived in `archive/aws-workflows/` (larchanka-training/dmc-1-t2-notebook-mono#245), API default provider migrated to OpenRouter (larchanka-training/dmc-1-t2-notebook-api#103, larchanka-training/dmc-1-t2-notebook-mono#247), tracking issue larchanka-training/js-notebook#186 closed on 2026-09-22; host `.env.prod` cleanup and AWS IAM key revocation remain pending operational confirmation under Phase G |
| 2026-09-24 | Aeza production post-cutover verified deployment summary | Done; larchanka-training/dmc-1-t2-notebook-mono#248 merged, factual milestone timeline and health evidence documented in `docs/aeza-production-observation-report.md`, continuous observation remains pending in Phase G |
| 2026-10-04 | Off-host backup restore verification drill runbook | Done; drill runbook and 16-point evidence checklist (E-01–E-16) merged in larchanka-training/dmc-1-t2-notebook-mono#250 ([`docs/backup-restore-drill-runbook.md`](./backup-restore-drill-runbook.md)) |
| 2026-10-09 | Change-impact verification tiers | Done; scoped verification requirements to change impact merged in larchanka-training/dmc-1-t2-notebook-mono#255 ([`AGENTS.md`](../AGENTS.md), [`docs/qa/qa-plan.md`](./qa/qa-plan.md)) |
| 2026-10-09+ | Skill Evolution v2 observation window | In progress; evidence audit and risk-triggered Operations/Recovery pass merged in larchanka-training/dmc-1-t2-notebook-mono#252, active 4–6 week experiment telemetry ledger running in [`docs/experiments/skill-evolution-v2-log.md`](./experiments/skill-evolution-v2-log.md) (started 2026-10-09T05:59:27Z, earliest closeout 2026-11-06) |
| 2026-10-04+ | Host backup cron activation and off-host restore verification drill execution | Pending; requires recorded E-01–E-16 evidence per the drill runbook sign-off protocol; closes the `aeza-migration-implementation-plan.md` §5 operational sign-off gate "Automated off-host backups run and a restore was tested" (historical DR runbook in larchanka-training/js-notebook#158) |
| 2026-10-04+ | Step 9: Notebook Versioning (snapshotting, revision history) | Candidate feature; architectural design and data model planning deferred until Phase G operational gates complete |

Production now runs on Aeza under the isolated `jsnotes-production` Compose
project. `deploy-aeza-production.yml` is the sole active production workflow;
legacy AWS, Beget, and staging deployment paths are retired (`archive/aws-workflows/`
and `archive/beget-workflows/`). OpenRouter is the active production cloud LLM
provider (`larchanka-training/js-notebook#186` closed 2026-09-22), with access restricted
to allowlisted accounts with Step 8e database usage ledgers and fail-closed reservations.

---

## Functional Requirements

### Notebooks

| Feature | Description |
|---|---|
| Create a notebook | The user can create a new notebook |
| Notebook list | View and manage existing notebooks |
| Delete / rename | Basic CRUD operations on notebooks |

### Blocks (Cells)

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
- Backend routing for low-memory/resource-heavy cell execution is a future extension — see [`execution-architecture.md`](./execution-architecture.md)
- Output (`console.log`, charts, errors) is displayed directly below the block
- The cell runtime executes JavaScript; TypeScript generation/validation support in the Cloud API does not by itself provide a browser execution transpiler

### Data Storage

- **Locally**: notebooks are saved in the browser's `IndexedDB` — fully offline operation
- **Format**: a JSON notebook structure (an array of blocks with a type, content, and metadata)
- **Cloud synchronization**: automatic background autosync for signed-in users (no manual button), requires authorization

### Accounts and Synchronization

- Passwordless email OTP sign-in via Resend; JWT access tokens and rotating refresh tokens
- Notebooks are pushed to the server **automatically in the background** after each local autosave
- Cell-level Last-Write-Wins by `updatedAt`, server wins ties; `deletedCells` carries deletion tombstones
- Current logout retains IndexedDB data. Planned device policy defaults new sessions to untrusted/in-memory; trusted persistence is opt-in. Before discarding unsynced memory on logout, attempt bounded final sync and, if edits remain unsaved, require an explicit discard/cancel choice before clearing. See [device-policy scope](./System_Architecture.md#35-local-storage-indexeddb) and [larchanka-training/js-notebook#136](https://github.com/larchanka-training/js-notebook/issues/136)

### LLM — Code Generation

- The user adds a text block with a description of the desired code
- Clicks the **"Generate code"** button
- The LLM returns a ready-made code block, which is inserted right after the text block
- The user can edit and explicitly run the generated code; insertion does not execute it
- The inserted result is currently an ordinary saved cell. Proposal/accept/reject remains a future UX requirement

---

## System Architecture

```text
React / CodeMirror 6 / Reatom
  ├─ QuickJS/WASM worker → notebook output
  ├─ WebLLM/WebGPU → local generation
  └─ IndexedDB v4 ↔ background autosync
                       │ HTTPS / JSON REST
                       ▼
FastAPI on Aeza
  ├─ OTP / JWT sessions → Resend
  ├─ SQLAlchemy → PostgreSQL 16 (Liquibase migrations)
  └─ LLM proxy → OpenRouter
```

Cloud requests go through the backend to protect provider keys and enforce
access, rate limits and database-backed usage reservations. Local WebLLM
inference runs in the browser after model assets have been downloaded.
See [system architecture](./System_Architecture.md) for storage and runtime
boundaries, and [AI architecture](./ai-architecture.md) for T1/T2 differences.

## Technology Stack (Implemented)

- **Frontend:** React 19, TypeScript, Vite, CodeMirror 6, Reatom, `idb`.
- **Execution/output:** QuickJS/WASM in a Worker; separate sandboxed HTML output.
- **Backend:** FastAPI, SQLAlchemy 2.0, PostgreSQL 16, Liquibase.
- **Authentication:** passwordless Email OTP via Resend, JWT and refresh sessions.
- **AI:** WebLLM local inference or the server-side OpenRouter proxy.
- **Hosting:** Aeza Docker Compose, nginx, immutable GHCR image tags.

Python runtime, CI baseline and minimum supported version are distinguished in
[System Architecture §6](./System_Architecture.md#6-technology-stack).
Notebook cells live in `notebooks.notebooks.cells` (JSONB); auth/LLM usage
tables live in `users`, and AI context in `notebooks.notebook_ai_context`.

---

## Notebook Storage Format (JSON)

```json
{
  "formatVersion": 1,
  "id": "f47ac10b-58cc-4372-a567-0e02b2c3d479",
  "title": "My Notebook",
  "createdAt": 1735689600000,
  "updatedAt": 1736899200000,
  "cells": [
    {
      "id": "9b2e4c1a-7d3f-4a2b-8c1e-2d4f6a8b0c1e",
      "kind": "markdown",
      "content": "## Description",
      "updatedAt": 1736899200000
    },
    {
      "id": "3f1d8e7b-5a2c-4e9d-b6f1-0a3c5e7d9b1f",
      "kind": "code",
      "content": "const data = [1, 2, 3]; console.log(data);",
      "updatedAt": 1736899200000
    }
  ]
}
```

Timestamps are epoch milliseconds; cell order is array order. Selected rich
outputs persist separately in IndexedDB v4's local-only `outputs` store and
are absent from this sync format. See [System Architecture §5](./System_Architecture.md#5-notebook-storage-format).

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

- Device policy, legacy local-data migration and unsaved-edit handling in larchanka-training/js-notebook#136
- Pinned OpenRouter guard evaluation and T1/T2 context parity
- The data retention policy and GDPR
- Remaining Phase G evidence: continuous observation, automated encrypted off-host backup/restore and AWS credential cleanup
