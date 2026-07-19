---
name: spec-roadmap-maintainer
description: "Maintain JS Notebook specification review and roadmap artifacts stored outside the monorepo. Use when a task explicitly concerns specs or their roadmap: reviewing or prioritizing specs, classifying them as stale/partial/canonical/future, creating summary or learning material, building an implementation roadmap, or continuing an already active spec-roadmap workflow one step at a time."
---

# Spec Roadmap Maintainer

## Overview

Use this skill to keep JS Notebook specs executable and honest. A stale spec is
treated as a planning risk, not as implementation authority.

## Repository boundary

This skill is versioned in the public `dmc-1-t2-notebook-mono` repository, but
the source specifications and generated roadmap artifacts are maintained in an
outer workspace repository. They are deliberately not duplicated under this
monorepo's `docs/` directory.

Resolve `SPEC_ROOT` before reading or writing artifacts:

1. Prefer an explicit path supplied by the user.
2. When the monorepo is checked out as an outer workspace's `project/`
   directory, use `../docs/specs` from the monorepo root.
3. Otherwise ask for the specification repository or path. Do not create a new
   monorepo `docs/specs/` tree as a fallback.

Keep version-control actions in the repository that owns each file. If the
outer workspace has no remote, leave its artifacts local and report that fact;
do not copy them into the monorepo merely to publish them.

## Workflow

1. From the monorepo root, load project context first:
   - `AGENTS.md`
   - `.agents/skills/notebook-planner/SKILL.md`
2. Resolve `SPEC_ROOT`, then read the target specs there.
3. Check implementation evidence before assigning priority:
   - backend code under `api/app/modules/`;
   - frontend code under `ui/src/`;
   - architecture docs under monorepo `docs/`;
   - tests and OpenAPI snapshots when contracts are involved.
4. Classify each spec as one of:
   - `canonical`
   - `partial`
   - `stale`
   - `future`
   - `blocked`
   - `deferred`
5. Create or update durable artifacts:
   - `$SPEC_ROOT/spec-roadmap-summary.md`
   - `$SPEC_ROOT/spec-roadmap-learning-material.md`
   - `$SPEC_ROOT/implementation-roadmap.md`
   - `$SPEC_ROOT/spec-index.md` when a full status map is needed.
6. For implementation roadmaps, split work by submodule boundary:
   - `api/` first for API contracts and backend behavior;
   - `ui/` second for consumers;
   - monorepo docs/pointers after submodule PRs.

## Roadmap execution rule

This rule applies only when the current conversation is explicitly about the
specification roadmap, or the user has identified the roadmap file or step.
The phrase `take next step` by itself must not redirect an unrelated workflow
(for example, a PR chain) into specification-roadmap execution.

When `$SPEC_ROOT/implementation-roadmap.md` exists and that roadmap context is
active, do not continue executing tasks by momentum. Wait for the user command:

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
grep -RInE "canonical|partial|stale|future|blocked|deferred|take next step" "$SPEC_ROOT" .agents/skills/spec-roadmap-maintainer
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
