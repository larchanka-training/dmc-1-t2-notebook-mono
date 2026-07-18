---
id: jsnb-spec-roadmap-learning-material-20260719
title: "Learning material — reading stale specs against implementation"
project: jsnb
type: learning-material
status: active
tags: [project:jsnb, type:learning-material, status:active, topic:spec-roadmap]
created: 2026-07-19
updated: 2026-07-19
---

# Learning material — reading stale specs against implementation

## Core lesson

A spec is not current just because it is in `docs/specs/`. In this project,
planning documents must be checked against:

1. newer specs or implementation plans;
2. architecture docs;
3. API/UI code;
4. tests and OpenAPI snapshots.

If those sources disagree, do not implement the oldest spec literally. First
classify the mismatch and create a roadmap step to resolve it.

## Useful classification

| Classification | Meaning | Action |
|---|---|---|
| `canonical` | This is the current source of truth. | Implement against it. |
| `partial` | Some acceptance criteria are already implemented, others are not. | Split completed and remaining scope. |
| `stale` | The document conflicts with newer code or decisions. | Mark stale and replace/supersede before implementation. |
| `future` | Valid direction, but not current scope. | Keep as roadmap item with dependencies. |
| `blocked` | Needs an external decision or security/architecture answer. | Capture the blocker before coding. |

## Example: backend execution

The old backend execution spec says users should choose Browser/Server and
server code should run in Docker. Current implementation evidence says:

- `/api/v1/execute` exists, but it is a debug/fallback endpoint;
- it is disabled by default;
- the runner is a Node subprocess, not a production sandbox;
- the more recent issue #73 plan keeps `/execute` outside core Notebook API
  scope.

Correct conclusion: split the topic into two tracks:

1. current debug/fallback `/execute` contract and safety documentation;
2. future production sandbox execution.

## Roadmap discipline

Each roadmap task should be independently reviewable:

- one clear outcome;
- explicit touched surfaces;
- acceptance criteria;
- verification commands;
- dependencies;
- risk notes.

For this repo, split tasks at submodule boundaries:

- API contract and backend implementation happen in `project/api`;
- UI consumer work happens in `project/ui`;
- monorepo docs/pointer updates happen after submodule PRs;
- docs-only planning artifacts can live in root `docs/specs/`.

## `take next step` workflow

When a roadmap exists, the agent should not keep implementing by momentum.
The workflow is:

1. Find the first incomplete roadmap step.
2. Confirm it is still safe and unblocked.
3. Execute only that step.
4. Verify it.
5. Update the roadmap status.
6. Stop and wait for the next `take next step`.

This keeps large feature programs reviewable and prevents hidden scope creep.
