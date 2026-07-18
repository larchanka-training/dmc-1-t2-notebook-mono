---
id: jsnb-spec-implementation-roadmap-20260719
title: "JS Notebook Specs — implementation roadmap"
project: jsnb
type: roadmap
status: active
tags: [project:jsnb, type:roadmap, status:active, topic:spec-roadmap]
created: 2026-07-19
updated: 2026-07-19
---

# JS Notebook Specs — implementation roadmap

## Operating rule

This is the main roadmap for the reviewed specs. Execute it incrementally.

Only start the next task when the user says:

```text
take next step
```

After each step, update this document with status/evidence and stop.

Status values:

- `todo` — not started;
- `in_progress` — active current step;
- `done` — implemented and verified;
- `blocked` — cannot proceed without a decision or external state;
- `deferred` — valid future scope, intentionally not next.

## Roadmap overview

| Order | Priority | Status | Workstream | Output |
|---:|---|---|---|---|
| 1 | P0 | todo | Docs cleanup and canonical spec map | Specs marked canonical/partial/stale/future. |
| 2 | P0 | todo | Backend execution split | Separate debug `/execute` doc from future production sandbox doc. |
| 3 | P1 | todo | Compression | gzip/brotli or CDN compression verified. |
| 4 | P1 | todo | Code splitting | Lazy route/page loading and bundle impact verified. |
| 5 | P1 | todo | Auth token doc/policy sync | Auth docs match refresh/logout/single-flight behavior and remaining trusted-device gaps. |
| 6 | P2 | todo | Graphical output completion | Rendering, persistence, API, and export expectations aligned. |
| 7 | P2 | todo | Export completion | Decide frontend-only vs backend export; add `.ipynb` if in scope. |
| 8 | P2 | todo | LLM provider toggle | Security-reviewed provider configuration plan. |
| 9 | P3 | deferred | Notebook versioning | Version model/API/UI after sync is stable. |
| 10 | P3 | deferred | Sharing and collaboration | Permissions/public access/collaboration architecture. |
| 11 | P3 | deferred | Admin user blocking | Admin moderation after auth/session policy stabilizes. |
| 12 | P3 | deferred | Authors page refresh | Evidence-based content refresh only if needed. |

## Step 1 — Docs cleanup and canonical spec map

**Priority:** P0  
**Status:** todo  
**Size:** M  
**Touched surfaces:** `docs/specs/`

### Goal

Make it clear which spec files are canonical, partial, stale, future, or
deferred before any implementation starts.

### Subtasks

1. Add a `docs/specs/spec-index.md` with every reviewed spec and its status.
2. Mark `implementation-plan-v2_ru.md` as canonical for issue #73 Notebook API.
3. Mark `01_Backend_Code_Execution.md` as stale/needs split rather than current
   production scope.
4. Mark specs 10 and 11 as next P1 performance work.
5. Link this roadmap, the summary, and the learning material from the index.

### Acceptance criteria

- A reader can identify the current source of truth for #73 without reading
  every legacy spec.
- Stale backend execution requirements are not presented as ready-to-code.
- Each spec has a status and next action.

### Verification

```bash
rg -n "canonical|partial|stale|future|deferred" docs/specs
```

## Step 2 — Split backend execution into current and future tracks

**Priority:** P0  
**Status:** todo  
**Size:** M  
**Touched surfaces:** `docs/specs/backend-notebooks-execute/`,
`project/docs/execution-architecture.md` if the canonical architecture needs
clarification.

### Goal

Prevent the current debug/fallback `/execute` endpoint from being mistaken for
safe production server execution.

### Subtasks

1. Create a current-state doc for debug/fallback `/api/v1/execute`.
2. Create or rewrite a future-state doc for production sandbox execution.
3. State explicitly that current Node subprocess execution is not production
   sandboxing.
4. Preserve future requirements: isolation, resource limits, output contract,
   UI routing/toggle, and load/security testing.
5. Add a migration path from current debug endpoint to production sandbox.

### Acceptance criteria

- Current and future execution tracks are separate.
- Production user-facing server execution remains blocked on real sandboxing.
- No doc implies Docker/gVisor isolation already exists.

### Verification

```bash
rg -n "debug/fallback|not.*production sandbox|ENABLE_EXECUTE|future production" docs/specs/backend-notebooks-execute project/docs/execution-architecture.md
```

## Step 3 — Enable and verify compression

**Priority:** P1  
**Status:** todo  
**Size:** S/M  
**Touched surfaces:** `project/proxy/`, possibly deployment docs.

### Goal

Reduce cold-load transfer size for static frontend assets.

### Subtasks

1. Decide whether compression is owned by nginx origin or Cloudflare.
2. If nginx-owned, add gzip/brotli configuration compatible with the deployed
   image.
3. If Cloudflare-owned, document the setting and verification path.
4. Verify `Content-Encoding: br` or `gzip` for JS/CSS assets.
5. Capture before/after evidence in docs or release notes.

### Acceptance criteria

- JS/CSS assets are served compressed in production or documented as compressed
  by CDN.
- Headers are verified with a repeatable command.
- App still loads with COOP/COEP headers intact.

### Verification

```bash
curl -I -H 'Accept-Encoding: br, gzip' https://jsnb.org/assets/<asset>.js
curl -I -H 'Accept-Encoding: br, gzip' https://jsnb.org/assets/<asset>.css
```

## Step 4 — Implement route-level code splitting

**Priority:** P1  
**Status:** todo  
**Size:** M  
**Touched surfaces:** `project/ui/`

### Goal

Stop loading every page module in the initial frontend bundle.

### Subtasks

1. Audit current eager imports in `project/ui/src/app/App.tsx`.
2. Identify route/page modules safe for lazy loading.
3. Add route-level lazy imports with loading fallback.
4. Keep notebook critical path stable.
5. Measure bundle output before/after.

### Acceptance criteria

- Initial JS bundle is smaller.
- Non-critical pages load dynamically.
- Route navigation still works.
- UI tests/typecheck pass.

### Verification

```bash
cd project/ui
pnpm test
pnpm typecheck
pnpm build
```

## Step 5 — Auth token docs and trusted-device policy sync

**Priority:** P1  
**Status:** todo  
**Size:** M  
**Touched surfaces:** `project/api/docs/auth.md`, `project/ui/docs/auth.md` if
present, auth specs.

### Goal

Align auth specs with implemented refresh/logout/session-expiry behavior and
separate already-implemented work from policy gaps.

### Subtasks

1. Compare spec `04_Authentication_Token_Handling.md` with backend refresh
   services and frontend refresh middleware.
2. Document current refresh-token storage model.
3. Mark HttpOnly-cookie/trusted-device requirements as implemented, partial, or
   future.
4. Add remaining risks and test cases.
5. Keep API/UI auth docs paired if either is changed.

### Acceptance criteria

- Docs match actual access-token refresh and logout behavior.
- Remaining trusted-device work is explicit.
- No doc promises HttpOnly cookie behavior unless implemented.

### Verification

```bash
rg -n "refresh|logout|trusted|HttpOnly|single-flight" project/api/docs project/ui/docs docs/specs
```

## Step 6 — Complete graphical output contract

**Priority:** P2  
**Status:** todo  
**Size:** L, split before coding  
**Touched surfaces:** `project/ui/`, `project/api/`, docs.

### Goal

Make image/html/rich outputs consistent across runtime, UI rendering,
persistence, backend execution, and export.

### Subtasks

1. Document current `OutputItem` shape and rendered item types.
2. Decide which output types are persisted in Notebook JSON.
3. Add payload size limits for base64 images and HTML.
4. Align backend execution response schemas with UI output types.
5. Extend export behavior for image/html outputs.
6. Add rendering, persistence, and export tests.

### Acceptance criteria

- Output types have one canonical contract.
- Large rich outputs have explicit limits.
- Export behavior is defined for each output type.

### Verification

```bash
cd project/ui
pnpm test
cd ../api
pytest tests/test_execution.py
```

## Step 7 — Complete export feature

**Priority:** P2  
**Status:** todo  
**Size:** L, split before coding  
**Touched surfaces:** `project/api/`, `project/ui/`, docs, OpenAPI if backend
export is chosen.

### Goal

Resolve the gap between current frontend-only JSON/Markdown export and the spec
that requires backend `.ipynb`/`.md` export.

### Subtasks

1. Decide whether export remains frontend-only or moves to backend.
2. Add `.ipynb` contract if backend export is selected.
3. Define how outputs and images map to Markdown and Jupyter.
4. Add UI export menu options.
5. Add API route and OpenAPI sync if backend export is selected.
6. Add validation tests for generated files.

### Acceptance criteria

- Export scope is explicit: frontend-only or backend.
- `.md` and `.ipynb` behavior is testable.
- Existing JSON/Markdown export is not regressed.

### Verification

```bash
cd project/ui
pnpm test
cd ../api
pytest
python scripts/openapi.py bump --dry-run
```

## Step 8 — LLM provider toggle security plan

**Priority:** P2  
**Status:** todo  
**Size:** M  
**Touched surfaces:** `project/api/`, `project/ui/`, LLM docs/specs.

### Goal

Decide safely whether users may provide custom LLM endpoint/API key, and how
that interacts with current WebLLM and Bedrock paths.

### Subtasks

1. Map current provider paths: in-browser WebLLM and backend Bedrock.
2. Decide whether custom endpoint is allowed, and under which restrictions.
3. Define API-key handling: client-only, server proxy, or unsupported.
4. Threat-model SSRF, key leakage, logging, abuse/rate limiting, and CORS.
5. Update spec before coding.

### Acceptance criteria

- No custom endpoint implementation starts before security decision.
- API-key storage/logging policy is explicit.
- Default provider behavior remains clear.

### Verification

```bash
rg -n "Bedrock|WebLLM|api key|endpoint|provider|rate limit|log" docs project/api/app/modules/llm project/ui/src
```

## Step 9 — Notebook versioning

**Priority:** P3  
**Status:** deferred  
**Size:** L, split before coding  
**Depends on:** stable notebook persistence/sync.

### Goal

Allow users to create, view, and restore notebook versions without data loss.

### Subtasks

1. Define version data model.
2. Decide full snapshot vs delta storage.
3. Add backend API and migrations.
4. Add UI for create/list/view/restore.
5. Add restore safety behavior.

## Step 10 — Sharing and collaboration

**Priority:** P3  
**Status:** deferred  
**Size:** L/XL, architecture first  
**Depends on:** auth/access-control maturity and conflict strategy.

### Goal

Add private sharing, public read links, and eventually collaborative editing.

### Subtasks

1. Define permissions model.
2. Define public-token model.
3. Update notebook authorization checks.
4. Add sharing UI.
5. Add real-time collaboration only after access-control is stable.

## Step 11 — Admin user blocking

**Priority:** P3  
**Status:** deferred  
**Size:** M/L  
**Depends on:** auth/session invalidation policy.

### Goal

Let admins block/unblock users and revoke active sessions.

### Subtasks

1. Add user blocking fields.
2. Add admin authorization policy.
3. Add block/unblock API.
4. Revoke sessions on block.
5. Add admin UI if product scope requires it.

## Step 12 — Authors page evidence refresh

**Priority:** P3  
**Status:** deferred  
**Size:** S  
**Touched surfaces:** `project/ui/`, docs if source-of-truth contributor data
is documented.

### Goal

Refresh authors/contributors content only if current wording is inaccurate or
needs stronger evidence.

### Subtasks

1. Check merged PRs/issues for contributor evidence.
2. Update page copy conservatively.
3. Run focused UI tests.

## Current cursor

Next command:

```text
take next step
```

will start **Step 1 — Docs cleanup and canonical spec map**.
