---
id: jsnb-spec-roadmap-summary-20260719
title: "JS Notebook Specs Roadmap — summary"
project: jsnb
type: summary
status: active
tags: [project:jsnb, type:summary, status:active, topic:spec-roadmap]
created: 2026-07-19
updated: 2026-07-19
---

# JS Notebook Specs Roadmap — summary

## Decision

Use the current implementation evidence to reorder the specs. The next work is
not to start backend execution from scratch. The next work is:

1. clean up stale/partial specs;
2. make the roadmap the canonical planning document;
3. execute the roadmap one step at a time only after the command
   `take next step`.

## Current state

The specs in `docs/specs/` mix three states:

- already implemented or partially implemented work;
- stale plans that conflict with current code;
- future product features that are too large to start before the core docs and
  performance baseline are aligned.

The main drift is in backend execution:

- `docs/specs/backend-notebooks-execute/01_Backend_Code_Execution.md` describes
  a user-facing Browser/Server switch and Docker-style server sandbox.
- `docs/specs/backend-notebooks-execute/implementation-plan-v2_ru.md` says
  `/api/v1/execute` is stretch/future scope for issue #73.
- `project/api/app/modules/execution/controllers/execution_controller.py`
  documents the implemented endpoint as debug/fallback, disabled by default.
- `project/api/app/modules/execution/services/runner.py` explicitly says the
  current Node subprocess runner is not a production sandbox.

## Priority bands

| Priority | Workstream | Reason |
|---|---|---|
| P0 | Docs cleanup and backend execution split | Prevents unsafe interpretation of debug execution as production sandboxing. |
| P0 | Production execution safety boundary | Server execution cannot be user-facing until sandboxing is real. |
| P1 | Compression | Low-risk performance win; nginx prod config has no visible gzip/brotli setup. |
| P1 | Code splitting | Current app imports all pages eagerly; this directly conflicts with the lazy-loading spec. |
| P1 | Auth token doc/policy sync | Refresh/logout/single-flight exist, but docs and trusted-device policy need alignment. |
| P2 | Graphical output | UI rendering exists; persistence/export/API consistency remains. |
| P2 | Export | Frontend JSON/Markdown export exists; backend `.ipynb` export does not. |
| P2 | LLM provider toggle | Requires security review before custom endpoint/API-key support. |
| P3 | Versioning | Depends on stable notebook persistence/sync semantics. |
| P3 | Sharing and collaboration | Requires access-control, security, and conflict model work. |
| P3 | Admin blocking | Useful after auth/session invalidation policy is fully settled. |
| P3 | Authors page | Appears implemented; only evidence/content refresh remains if needed. |

## Execution rule

Do not batch roadmap execution. For this roadmap, each implementation step
starts only when the user says:

```text
take next step
```

At that point, perform the first incomplete roadmap step, update durable
artifacts if needed, verify the step, and stop.
