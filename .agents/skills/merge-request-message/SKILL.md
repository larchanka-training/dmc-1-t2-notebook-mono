---
name: merge-request-message
description: >
  Compose a pull request description for JS Notebook based on git
  history, branch ticket, and project conventions (PR template,
  submodule discipline, doc sync). Stops before `gh pr create` and
  waits for explicit user approval to publish.
globs:
  - ".git/HEAD"
  - ".agents/pr-drafts/**"
---

# Compose Pull Request Description

Use this workflow to generate a structured PR description for the current
branch, grounded in this monorepo's history, conventions, and submodule
discipline.

> The skill is named `merge-request-message` for portability across hosting
> platforms. In this repo we use GitHub, so "PR" and "MR" mean the same
> thing — the produced document is a GitHub PR description.

## Prerequisites

- You are on the feature branch for which the PR is being created
  (not `main`).
- Commits follow the project convention documented in
  [`.agents/rules/commit-message-rule.md`](../../rules/commit-message-rule.md)
  — one of three accepted patterns (`TARDIS-NN:`, Conventional
  Commits, or plain imperative). The PR title will become the
  squash-merge commit subject — write it as a subject.
- If submodule pointers (`api/`, `ui/`) are bumped — the corresponding
  submodule commits are already pushed to their remotes
  (see `AGENTS.md` §7 — push order).

## Step 1: Identify the ticket and the issue's home repo

1. Determine the current branch and current repo:

```bash
git branch --show-current
git config --get remote.origin.url    # which repo is this PR being opened in?
```

   Record both. The repo where the PR opens (current) vs. the repo
   where the issue lives can differ — that's the cross-repo case
   that decides the trailer form (Step 4.5).

2. Extract the ticket key from the branch name if present:
   - Look for `TARDIS-NN` in the branch slug
     (e.g. `feature/TARDIS-15-bump-submodules`).
   - If no ticket key is present — proceed without one. Trailer
     form is decided in Step 4.5.

3. If a GitHub issue is linked to this work, fetch its description.
   **Ask the user which repo the issue lives in** — it is usually
   the monorepo `dmc-1-t2-notebook-mono`, even when the PR itself
   is opened in an `api/` or `ui/` submodule repo:

```bash
# replace <repo> with the repo where the ISSUE lives (often the monorepo)
gh issue view <NN> --repo larchanka-training/<repo>
```

   `<NN>` is the GitHub issue number (e.g. `3`, `60`, `69`). It is
   **not** necessarily the same as the TARDIS ticket number — they
   live in different trackers. Ask the user if unclear.

   Record three pieces of info to carry into Step 4.5:

   - **issue repo** (e.g. `larchanka-training/dmc-1-t2-notebook-mono`)
   - **issue number** (e.g. `3`)
   - **PR repo** (from `git config --get remote.origin.url`)

4. If neither a TARDIS ticket nor a GitHub issue is available — use the
   branch name and commit subjects as the only context. There will
   be no `Closes` / `Refs` trailer.

## Step 2: Gather commit history for this branch

5. List commits on this branch not in `main`:

```bash
git log --oneline main..HEAD
```

6. Full commit messages including bodies:

```bash
git log --format="### %h: %s%n%n%b" main..HEAD
```

## Step 3: Identify changed files (incl. submodules)

7. File-level diff summary:

```bash
git diff --stat main..HEAD
```

8. If submodule pointers are bumped — inspect what changed inside the
   submodule. Pointer-only changes hide all the real work:

```bash
# inside api/
cd api && git log --oneline $(git -C .. ls-tree main api | awk '{print $3}')..HEAD
```

   Repeat the same in `ui/` if its pointer moved.

## Step 4: Create the PR document

9. Write the draft to:

```
.agents/pr-drafts/<branch-or-ticket>-pr.md
```

   The directory is gitignored (see repo `.gitignore`) — drafts stay
   local and do not pollute the working tree.

10. Use this structure (Russian by default; switch to English if the
    PR is doc-translation work or the team has agreed for this PR):

```markdown
# Draft: TARDIS-NN: <Task title> | <Short imperative if no ticket>

## Problem

<2–3 sentences. What was broken or missing, what user/system pain it
caused. Avoid implementation details — those go in Solution.>

## Solution

<What was done and why this particular approach. Call out cross-
submodule changes explicitly: "Bumped api pointer to include the new
auth endpoint (PR #NN in api); ui consumes regenerated openapi types.">

## Verification

- [ ] Local checks passed: `pytest` (api), `pnpm test` / `pnpm lint` /
      `pnpm typecheck` (ui)
- [ ] Relevant GitHub Actions green: API CI, UI CI, Docker Compose CI
      (only the ones that ran for this PR — see
      `docs/github-actions-pr-checks.md` on `paths` filters)
- [ ] Docker build verified locally if the runtime image or Dockerfile
      changed
- [ ] **Submodule discipline**: if `api/` or `ui/` pointer bumped — the
      submodule commit is pushed to its remote and reachable
- [ ] **auth.md sync**: if `auth.md` touched in one submodule, the
      counterpart in the other was updated in the same scope of work
      (`AGENTS.md` §10)
- [ ] **OpenAPI sync**: if the API contract changed —
      `api/docs/openapi.json` regenerated (`scripts/openapi.py dump`)
      and ui types refreshed via `pnpm api:generate`
- [ ] **Docs sync**: any document in `/docs` whose logic this PR
      changes was updated in the same PR (`AGENTS.md` §9)

## Known issues

<Optional. Problems discovered during development with links to created
GitHub issues. Omit the section if none.>

- **<problem>** — <description> — #<issue-number>

## Screenshots

<Required for UI changes (Before/After), omit otherwise.>

| Before | After |
|--------|-------|
| ![before](<url>) | ![after](<url>) |

## Notes

<Optional. Omit if nothing to add.>

- Known limitations
- Related tickets: "See also TARDIS-YYY" / "Continues #NN"
- TODO items out of scope for this PR
- Breaking changes (if any)

---
<ISSUE_TRAILER>           ← decided in Step 4.5 — do not hard-code
```

## Step 4.5: Decide the issue trailer (mandatory)

Before showing the draft to the user in Step 5, **compute the
trailer line** from the three pieces recorded in Step 1 (issue
repo, issue number, PR repo). Do not hand-write `Refs TARDIS-NN`
on autopilot — that string is plain text and does not link to
anything.

### Decision table

| Issue lives in | PR opens in | Trailer to use | Auto-close on merge? |
|---|---|---|---|
| Same repo as the PR | Same repo | `Closes #<NN>` | ✅ Yes |
| Monorepo (`dmc-1-t2-notebook-mono`) | Submodule (`api` or `ui`) | `Refs larchanka-training/dmc-1-t2-notebook-mono#<NN>` | ❌ No — close the issue from the **monorepo PR** instead (use `Closes #<NN>` there) |
| Different repo, any | Any | `Refs <owner>/<repo>#<NN>` | ❌ No |
| No GitHub issue (tracker-only TARDIS) | Any | `Refs TARDIS-NN` (plain text) **or** omit | ❌ No |
| No ticket at all | Any | Omit the trailer entirely | n/a |

### Cross-repo / multi-PR coordination

If the same task spans multiple PRs (typical: a contract change
needs both an api submodule PR and a monorepo pointer-bump PR,
both tied to one monorepo issue) — exactly **one** of the PRs uses
`Closes #<NN>`. The rest use `Refs <owner>/<repo>#<NN>`. By
convention the **monorepo PR** is the one that closes, because it
is the last to merge and represents the completed state of the
feature in the monorepo's view.

### Apply to the draft

Replace the `<ISSUE_TRAILER>` placeholder in the draft file with
the resolved string. **Never** leave `<ISSUE_TRAILER>` literal —
that's a bug to catch before Step 5.

Examples:

```
Closes #3                                                       # monorepo PR closing a monorepo issue
Refs larchanka-training/dmc-1-t2-notebook-mono#3                # api/ui PR referencing the same issue
Closes #28, Closes #42                                          # PR closing multiple same-repo issues
Refs TARDIS-15                                                  # tracker ticket without a GitHub issue
```

## Formatting rules

- **Language**: Russian by default — matches the majority of commit
  history. English is acceptable when the PR is itself about English
  content (e.g. doc translation) or the team has agreed for this PR.
- **Title format**: `Draft: TARDIS-NN: <title>` for ticketed work;
  otherwise `Draft: <short imperative summary>`. Title comes from the
  ticket subject when a ticket exists.
- **Problem**: concise, user/system impact. No filler phrases, no
  implementation detail.
- **Solution**: WHAT changed and WHY this approach. The HOW is visible
  in the diff and does not belong in the description.
- **Verification**: keep only the boxes that apply. Add PR-specific
  items if there are non-obvious manual steps a reviewer must run.
- **Known issues / Screenshots / Notes**: omit any section that is
  empty. An empty section is worse than no section.
- **Long copy in tables**: separate paragraphs with `<br>` inside table
  cells; outside tables, use blank lines.
- **Closes / Refs line**: decided in Step 4.5 by the decision
  table — do not hand-write `Refs TARDIS-NN` on autopilot. Bare
  `TARDIS-NN` strings are plain text; they do not link and GitHub
  does not auto-close anything on them. If the work has a GitHub
  issue, the trailer must link to it.

## Step 5: Review and confirm

11. Show the user the generated draft. **Stop here.** Do not call
    `gh pr create` yet.
12. Ask the user explicitly which they want:
    - Adjust wording, sections, or the verification checklist
      (iterate on the draft file).
    - Approve as-is — then proceed to Step 13.

13. **Only after the user gives explicit approval** (e.g. "looks
    good, open it", "ship it", "create the PR"), run
    `gh pr create`. Creating a PR is visible to the team — it
    notifies reviewers, kicks CI, and the PR URL is hard to
    untrigger. Approval to draft the description is **not**
    approval to publish it.

    Pre-publish checks (before running `gh pr create`):

    - [ ] `<ISSUE_TRAILER>` placeholder replaced (Step 4.5)
    - [ ] Trailer form matches the decision table (same-repo →
          `Closes #<NN>`; cross-repo → `Refs <owner>/<repo>#<NN>`)
    - [ ] No `Draft:` prefix in the title passed to `--draft`
    - [ ] `--body-file` points at the draft file the user approved
    - [ ] If submodule PR also coordinates with a monorepo PR —
          the companion PR URL is mentioned in the description
          (and the companion description back-references this one)

```bash
gh pr create \
  --title "TARDIS-NN: <title>" \
  --body-file .agents/pr-drafts/<file>-pr.md \
  --draft
```

    Drop the `Draft:` prefix from the title before passing it to
    `gh pr create --draft` — GitHub's own "Draft" state replaces it.

## Red flags

- **Submodule pointer bumped, but submodule commit not pushed** —
  reviewer can't fetch the new commit, CI fails on checkout. Stop the
  PR until the submodule push is confirmed.
- **`auth.md` modified in only one submodule** — the auth contract is
  diverging. The PR is unfinished (`AGENTS.md` §10).
- **API contract changed but `openapi.json` not regenerated** — ui
  types will lag. Block until the dump is committed.
- **Description says "see commits" with no Problem/Solution** — the PR
  is too coarse to review. Insist on at least 2–3 sentences in each.
- **No Verification checklist for a non-docs PR** — the reviewer has
  no idea what was actually checked.
- **`Refs TARDIS-NN` used when a GitHub issue exists** — the
  trailer is plain text and does not link. Replace with
  `Closes #<NN>` (same-repo) or `Refs <owner>/<repo>#<NN>`
  (cross-repo) per Step 4.5 decision table.
- **`Closes` trailer on a cross-repo issue** — GitHub does not
  auto-close issues across repositories. The trailer renders as a
  link but nothing closes on merge; the issue silently stays open.
  Use `Refs <owner>/<repo>#<NN>` and put `Closes` in the
  same-repo PR (typically the monorepo PR).
- **`<ISSUE_TRAILER>` placeholder shipped in the PR description**
  — Step 4.5 was skipped. Compute the trailer before Step 5.

## Related

**Primary** (load alongside this skill):

- [`.agents/rules/commit-message-rule.md`](../../rules/commit-message-rule.md)
  — accepted commit-subject patterns; PR title flows into squash
  subject
- `AGENTS.md` §7 — branch / PR / submodule conventions
- `AGENTS.md` §9 — documentation sync rule
- `AGENTS.md` §10 — `auth.md` synchronization between `api/` and `ui/`

**Secondary** (load only when the sub-topic comes up):

- `docs/github-actions-pr-checks.md` — what CI checks must pass and
  why some may be Skipped (`paths` filters)
- `docs/github-repository-settings.md` — repository PR rules and the
  base PR template
- `.agents/skills/notebook-pr-review/SKILL.md` — the reviewer's
  mirror of this checklist
- `.agents/skills/notebook-planner/SKILL.md` — task decomposition
  that produces the commits this skill summarizes
