# .agents/skills

Project-level skills for AI coding agents (Claude Code, Cursor, Copilot,
etc.) working in this monorepo. Each skill is a self-contained workflow
with rules, process, red flags and a verification checklist.

Skills here describe **how to work in this specific project**. Generic
framework rules live in submodule-local skills (e.g.
`ui/.agents/skills/reatom`, `ui/.agents/skills/fractal-frontend`).

## Skills

| Skill | Load when |
|---|---|
| [notebook-ui](./notebook-ui/SKILL.md) | Working inside `ui/` — features, pages, components, state, HTTP, Vitest |
| [notebook-api](./notebook-api/SKILL.md) | Working inside `api/` — FastAPI modules, SQLAlchemy, Liquibase, OpenAPI, pytest |
| [notebook-planner](./notebook-planner/SKILL.md) | Decomposing a task into submodule-aware steps before any code is written |
| [notebook-qa](./notebook-qa/SKILL.md) | QA strategy and test design — pick test level, map to qa-plan scenarios, plan manual checks |
| [notebook-quality-analysis](./notebook-quality-analysis/SKILL.md) | Independent verification of just-completed work — Ready / Ready with caveats / Not ready verdict with evidence |
| [notebook-pr-review](./notebook-pr-review/SKILL.md) | Reviewing a PR against this repo's submodule, doc and contract rules |
| [notebook-llm](./notebook-llm/SKILL.md) | LLM code-generation feature — three-tier fallback chain (WASM → backend → OpenAI), prompt validation, rate limits, secrets, UX policy |
| [merge-request-message](./merge-request-message/SKILL.md) | Composing a PR description from git history, branch ticket and project conventions |
| [spec-roadmap-maintainer](./spec-roadmap-maintainer/SKILL.md) | Reviewing/prioritizing `docs/specs`, creating summary + learning + roadmap artifacts, and executing roadmap steps only on `take next step` |

## Format

Every `SKILL.md` follows the same hybrid layout:

```markdown
---
name: <kebab-case>             # required — must match folder name
description: <one-paragraph    # required — trigger; what + when to load
              trigger;
              wrap > for
              multi-line>
globs:                         # optional — Cursor MDC-compatible file
  - "api/**/*.py"              # paths that imply this skill. Claude Code
  - "ui/src/**"                # uses `description` for routing; `globs`
                               # are forward-compat for other tools.
---

# <Title>

## Overview
## Instruction priority         # how this skill defers to AGENTS.md / docs
## When to use
## Process
## Red flags
## Verification
## Related                      # primary (load alongside) + secondary
                                #   (load on specific question)
```

Frontmatter rules:

- `name` and `description` are the only **required** fields. Don't
  add `schemaVersion`, `agent`, or other custom fields — they're
  not interpreted by any tool currently in the toolchain.
- `globs` is optional and forward-compatible — Claude Code routes on
  `description`, Cursor MDC honours `globs`. Adding both costs
  nothing and avoids a future migration.
- The frontmatter is YAML. Folded scalars (`>`) are fine for long
  descriptions; block scalars (`|`) preserve newlines if you need
  them.

Long supporting material goes into a sibling `references/` folder and is
loaded conditionally from the main `SKILL.md`.

Cross-skill shared snippets live under `_shared/` and are loaded by
direct cross-link from multiple skills (e.g.
`_shared/evidence-discipline.md` used by `notebook-qa`,
`notebook-quality-analysis`, `notebook-pr-review`).

## Related rules

Project-wide conventions that aren't skills (no workflow process,
just rules) live in [`.agents/rules/`](../rules/):

- [`commit-message-rule.md`](../rules/commit-message-rule.md) —
  accepted commit-subject patterns

## Adding a new skill

1. Create `.agents/skills/<name>/SKILL.md` with the frontmatter above.
2. Add a row to the table in this README.
3. Cross-link from related skills (`## Related` section).
4. If a doc in `/docs` is the source of truth for the topic, link to it
   instead of duplicating — skills point at docs, they don't replace them.
