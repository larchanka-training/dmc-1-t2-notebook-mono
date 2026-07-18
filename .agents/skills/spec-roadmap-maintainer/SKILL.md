---
name: spec-roadmap-maintainer
description: Maintain JS Notebook specification review and roadmap artifacts. Use when a task asks to review or prioritize docs/specs, mark specs as stale/partial/canonical/future, create summary or learning material from a spec review, build a step-by-step implementation roadmap, or continue roadmap execution with the command "take next step".
---

# Spec Roadmap Maintainer

## Overview

Use this skill to keep JS Notebook specs executable and honest. A stale spec is
treated as a planning risk, not as implementation authority.

## Workflow

1. Load project context first:
   - `AGENTS.md`
   - `project/AGENTS.md`
   - `.agents/skills/notebook-planner/SKILL.md`
2. Read the target specs under `docs/specs/`.
3. Check implementation evidence before assigning priority:
   - backend code under `project/api/app/modules/`;
   - frontend code under `project/ui/src/`;
   - architecture docs under `project/docs/` and `docs/architecture/`;
   - tests and OpenAPI snapshots when contracts are involved.
4. Classify each spec as one of:
   - `canonical`
   - `partial`
   - `stale`
   - `future`
   - `blocked`
   - `deferred`
5. Create or update durable artifacts:
   - `docs/specs/spec-roadmap-summary.md`
   - `docs/specs/spec-roadmap-learning-material.md`
   - `docs/specs/implementation-roadmap.md`
   - `docs/specs/spec-index.md` when a full status map is needed.
6. For implementation roadmaps, split work by submodule boundary:
   - `project/api` first for API contracts and backend behavior;
   - `project/ui` second for consumers;
   - monorepo docs/pointers after submodule PRs.

## Roadmap execution rule

When `docs/specs/implementation-roadmap.md` exists, do not continue executing
tasks by momentum. Wait for the user command:

```text
take next step
```

On that command:

1. Find the first `todo` or `in_progress` roadmap step.
2. Re-check that the step is still safe and unblocked.
3. Execute only that step.
4. Run proportional verification.
5. Update the roadmap status/evidence.
6. Stop and wait for the next command.

## Classification rules

- Mark a spec `canonical` only when newer docs and code do not contradict it.
- Mark a spec `partial` when some acceptance criteria are already implemented.
- Mark a spec `stale` when it conflicts with newer implementation evidence.
- Mark a spec `future` when it is valid direction but not current scope.
- Mark a spec `blocked` when it needs an architecture/security/product decision.
- Mark a spec `deferred` when it is lower priority and intentionally not next.

## Red flags

- A spec says a feature is safe, but code comments or architecture docs say it
  is debug/fallback or disabled by default.
- A roadmap step crosses `api`, `ui`, and monorepo without splitting.
- A contract change lacks OpenAPI and consumer regeneration tasks.
- Auth docs are updated on only one side.
- A large future feature is scheduled before P0 doc drift or safety gaps.

## Verification

For docs-only roadmap work:

```bash
rg -n "canonical|partial|stale|future|blocked|deferred|take next step" docs/specs project/.agents/skills/spec-roadmap-maintainer
```

For code-affecting roadmap steps, add the relevant checks from
`notebook-planner`, `notebook-api`, `notebook-ui`, and `notebook-qa`.

## Related

Primary:

- `../notebook-planner/SKILL.md`

Secondary:

- `../notebook-api/SKILL.md`
- `../notebook-ui/SKILL.md`
- `../notebook-qa/SKILL.md`
- `../notebook-quality-analysis/SKILL.md`
