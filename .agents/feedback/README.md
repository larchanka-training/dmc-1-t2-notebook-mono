# `.agents/feedback/`

Append-only log of skill usage outcomes — the seed of a feedback
loop that lets the team iterate on `.agents/skills/` from data
instead of vibes.

Currently a **scaffold**, not a tool. Entries are written by hand
(or by an agent prompted to write one) after a PR closes. A future
iteration may automate the capture (PR webhook → entry) or render
the log into a dashboard. Until then, the discipline is the point:
when a skill steers you wrong (or steers you right in a non-obvious
way), record it.

## How to use

1. After a PR merges (or after a notable agent session), copy
   `entry.template.md` to
   `entries/YYYY-MM-DD-<short-slug>.md`.
2. Fill in the front-matter and notes.
3. Commit alongside the PR or as a follow-up. Entries are not
   secret — they live in the repo.

The directory under `entries/` is gitignored only if the team
decides feedback should be local. Default is **tracked** — shared
learning beats individual hindsight.

## Schema (front-matter)

```yaml
---
date: 2026-05-23
pr: 60                                # optional: GitHub PR number
branch: feature/TARDIS-15-bump-submodules  # optional
skills_loaded:                        # which skills the agent had loaded
  - notebook-planner
  - notebook-ui
task_size: M                          # XS | S | M | L | XL (from planner)
outcome: shipped                      # shipped | reverted | abandoned | scope-creep
skill_helpful:                        # which skills made the work better
  - notebook-pr-review
skill_missed:                         # which skills would have helped but weren't loaded
  - notebook-llm
skill_steered_wrong:                  # skills that gave bad guidance for this case
  - notebook-ui                       # — and a note below about how
---
```

## Body

Free-form. The interesting fields are:

- **What the skill steered well or poorly.** Specific section
  references beat generalities (`notebook-ui §3 "Reatom + clearStack"
  caught it before merge`).
- **What was missing.** A rule the agent should have known but the
  skill didn't say.
- **Drift discovered.** A skill section that disagrees with the
  current code/docs. File a follow-up to fix the skill or the docs
  per `AGENTS.md` §9.

Three lines is fine. The signal is more entries with thin notes
than a few entries with essays.

## Aggregation (manual, until automated)

Once a month (or per sprint), skim entries and look for:

- **Repeated misses** — a skill that "should have been loaded" three
  times means the trigger description in its front-matter isn't
  matching the agent's heuristic. Tighten the `description` field.
- **Repeated wrong-steers** — a skill section that misled across
  multiple PRs. Either the section is wrong or it's missing a
  caveat. Fix in a PR; reference the entries.
- **Repeated drift** — when the same drift row keeps showing up,
  promote the fix from `AGENTS.md` §12 drift table to a real PR.

Document the changes in a single "skills retro" PR per cycle and
clear the corresponding rows from this log (or keep them — the
historical record is cheap).

## Cross-link

- `.agents/skills/README.md` — the skill catalogue this log
  measures
- `AGENTS.md` §12 — drift table; feedback entries that surface new
  drift go here first
