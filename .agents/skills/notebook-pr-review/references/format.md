# PR review format: severity, verdicts, output template

Load this reference when **authoring** the review comment — the
labels, verdicts, and output shape live here. The main
`SKILL.md` covers the process (five-axis sweep + seven sections);
this file covers how to write the result down.

## Comment severity

Tag every review comment with one of the labels below. Unlabeled
comments default to **Suggestion** (non-blocking).

| Label | Meaning | Blocks merge? |
|---|---|---|
| **Critical** | Security issue, data loss, broken core functionality, severe regression, or a hard violation of `AGENTS.md` §7 / §9 / §10 / §11 (submodule discipline, docs sync, `auth.md` sync, mandatory rules). | Yes |
| **Important** | Correctness bug, missing required test, risky design, or a project-rule violation flagged by the Process sections in the main skill (`@/shared/api/generated/**` import, ad-hoc DDL, dependency-bloat, etc.). | Yes |
| **Suggestion** | Optional improvement. Better naming, simpler implementation, alternative approach. | No |
| **Nit** | Minor style / formatting issue. Useful only if the project's lint won't catch it. | No |
| **FYI** | Informational. Context for the author, no action required. | No |

Examples:

```
**Critical:** `api/docs/openapi.json` is stale — the new `POST
/notebooks` route isn't in the snapshot. CI `bump --dry-run` will
fail. Run `python scripts/openapi.py dump` and commit.

**Important:** `useState` in `features/notebook/ui/Title.tsx` — use
`atom` per `notebook-ui` skill and `clearStack` rule.

**Suggestion:** the helper in `services/parser.ts` could be a pure
function instead of a class.
```

## Merge recommendation

End every review with **one** of these verdicts (and only one):

| Verdict | When to use |
|---|---|
| **Approve** | All checks green, no `Critical`/`Important` findings, you would merge this yourself. |
| **Approve with nits** | Mergeable now; only `Suggestion`/`Nit`/`FYI` comments remain. Author can address them or not. |
| **Request changes** | At least one `Critical` or `Important` finding. Author must fix and re-request review. |
| **Needs clarification** | Can't determine correctness without more context — intent, scope, hidden constraints, missing tests for an unfamiliar behaviour. Ask before deciding. |
| **Split recommended** | PR is too large to review safely (≳400 lines of non-mechanical diff), mixes refactor with behaviour change, or touches unrelated subsystems. Ask for splitting before deeper review. |

A review that ends without an explicit verdict is incomplete — it
leaves the author guessing whether to merge.

## Review output template

When producing a structured review (e.g. in a comment, a
`gh pr review` body, or for the `/review` command), use this shape.
Omit any section that has nothing in it.

```markdown
# PR Review: <PR title or change name>

## Verdict
<Approve | Approve with nits | Request changes | Needs clarification | Split recommended>

## Summary
<1–3 sentences: what the PR does, overall assessment, the gating
finding if any.>

## What I checked
- <which Process sections were walked>
- <which CI logs were opened, which checks are green/skipped/red>
- <whether the diff was opened in a browser / whether the dev stack
  was run locally>

## Blocking findings (Critical / Important)

- **Critical/Important:** <Finding, with file:line if applicable>
  - Why it matters: <consequence — broken contract, security, lost
    data, AGENTS.md §X violation>
  - Suggested fix: <concrete action>

## Non-blocking comments (Suggestion / Nit / FYI)

- **Suggestion/Nit/FYI:** <Comment>

## Test review

**Good:**
- <covered behaviour, edge case caught, regression test added>

**Missing or weak:**
- <behaviour not covered, missing failure-path test, etc.>

## Risk areas

- <Risk and why it matters: e.g. "auth.md §5.3 reuse-detection has
  no integration test yet">

## Final notes

<Anything the author needs to know before the next revision —
follow-up tickets, deferred items, context they may lack.>
```

## Cross-link

- `.agents/skills/notebook-pr-review/SKILL.md` — the review
  process this format serves
- `.agents/skills/_shared/evidence-discipline.md` — what counts as
  evidence in any of the sections above
