---
name: create-session-artifacts
description: Create the dated review, learning note, and memory summary records for one completed or reviewed task under js-notebook/docs/reviews, js-notebook/learning, and js-notebook/docs/memory/chat-summaries. Use after finishing a phase, review, migration, or documentation task.
---

# Skill: Create Session Artifacts

Create the dated review, learning, and memory records for one completed or reviewed task. Use this
shared skill from phase execution, plan review, migration, and documentation-only work.

## Usage

Inputs: task topic, date-time in `YYYYMMDD-HHMM`, changed files or review scope, verification result,
open risks, and the next-agent instruction.

## Steps

### 1. Create the review

Write `js-notebook/docs/reviews/<name_ai-agent>-<topic>-<YYYYMMDD-HHMM>.md`. Put findings first, ordered by
severity, then assumptions, recommendation, and verification gaps. For a clean review state that no
findings were found and name residual risk.

### 2. Create the learning note

Write `js-notebook/learning/<name_ai-agent>-<topic>-<YYYYMMDD-HHMM>.md`. Explain what changed or was decided,
why, tools/frameworks/patterns used, and stable English development terms or abbreviations.

### 3. Create the memory summary

Write `docs/memory//chat-summaries/<name_ai-agent>-chat-summary-<topic>-<YYYYMMDD-HHMM>.md` with this minimum shape:

```markdown
# AI Memory & Chat Summary: <Title>

**Date:** YYYY-MM-DD HH:MM (+04:00)
**Status:** <complete|blocked|review-only>

## Current State
<implemented, approved, historical, and deferred facts>

## Verification
<commands and results; explicitly list checks not run>

## Next Agent Instruction
<one safe next action or “wait for explicit `take next step`”>
```

Do not rewrite historical memory to make it look current. Add a dated correction when facts changed.

## Checklist

- [ ] All three files use the same topic and timestamp.
- [ ] Findings and unresolved risks are explicit.
- [ ] Verification includes `git diff --check` and any project checks that apply.
- [ ] Memory clearly separates current, proposed, historical, and blocked state.
- [ ] Next-agent instruction does not silently authorize the next phase.
