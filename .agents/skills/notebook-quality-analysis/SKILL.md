---
name: notebook-quality-analysis
description: >
  Independent quality verification of just-completed implementation
  in JS Notebook. Load AFTER implementation and BEFORE opening or
  merging a PR — checks correctness, test coverage, risks,
  regressions, maintainability, security, performance, operational
  readiness. Output is a Ready / Ready with caveats / Not ready
  verdict with evidence. For designing tests and QA strategy, use
  notebook-qa. For reviewing someone else's PR, use
  notebook-pr-review.
globs:
  - ".git/HEAD"
---

# notebook-quality-analysis

Independent verification that just-finished work is actually ready —
before opening or merging a PR.

This skill exists because:

- agent-written code often "looks correct" without ever being run
- failed test output gets missed when scrolling
- assumptions about behaviour leak into self-reports
- "should be safe" gets confused with "verified safe"

The output is a structured readiness report. Evidence comes first;
opinion comes last.

## Instruction priority

When this skill conflicts with `AGENTS.md`, `docs/qa-plan.md`, or
project-specific verification practice — follow the project source.
This skill is supplemental.

## When to use

Load after implementing a change, before opening or merging a PR.
Specifically:

- A feature implementation claims to be "done" — verify
- A bug fix is in — does it actually fix the bug + add a regression test?
- Agent-generated code claims to work — verify
- A task in a multi-task plan claims complete — verify
- Suspicion of regressions, missing edge cases, or hidden risks

Do **not** use this skill for:

- Designing tests, planning QA strategy, deciding which level a new test belongs to → `notebook-qa`
- Reviewing someone else's PR (deciding to Approve / Request changes) → `notebook-pr-review`
- Decomposing the task before implementation → `notebook-planner`

## Quality dimensions

Walk these for any non-trivial change. Skip a dimension only with a
stated reason ("no UI changed", "no DB changed").

### 1. Requirement fit

- Does the implementation match what the task artifact asked for?
- All acceptance criteria satisfied?
- Did anything unrelated get added (scope creep — `AGENTS.md` §11)?
- Did anything get missed?

### 2. Correctness

- Edge cases: empty / null / missing / boundary
- Race conditions, state inconsistencies, partial updates
- Date / time / timezone, pagination, filtering, sorting
- Error handling — paths that fail, not just paths that succeed
- Concurrency in conflict-resolution (`api/docs/auth.md` §8 LWW +
  tombstones) if notebook persistence touched

### 3. Test coverage

- Main success path tested?
- Failure paths tested?
- Edge cases tested?
- Would the tests fail if the implementation were broken? (Mental
  mutation test.)
- Regression test for the bug fix, if applicable?
- Tests verify behaviour, not implementation details?

### 4. Maintainability

- Functions / components in reasonable size
- Names clear
- Duplicated logic
- Hidden side effects
- Inconsistent with surrounding patterns
- Dead code, dead comments

### 5. Security

- Input validated at boundary (auth inputs especially — see
  `api/docs/auth.md`)
- Authorization checked, not just authentication
- Secrets not exposed (`AGENTS.md` §11 — no JWT secret, no OTP in
  `prod`, no LLM keys in responses, logs, or test fixtures)
- Untrusted data treated as untrusted (notebook content,
  LLM-generated code, external API responses)

### 6. Performance

- Queries bounded (no unbounded list pulls)
- Pagination on list endpoints
- No N+1
- Async / sync boundaries respected (api side)
- UI re-renders bounded (Reatom dependency tracking correct;
  no `useState` for shared state)

### 7. Operational readiness

- Required env vars listed (api side — `api/docs/auth.md` §12)
- Migration ordering safe — see
  `notebook-api/references/liquibase-migrations.md`
- Backward compatibility if a contract changed
- Logging via `structlog`, not bare `print()` (api)
- Rollback story stated if the change is risky

## Skills are heuristics, not proofs

A complete walk of the dimensions above and a green Verified table
are *necessary*, not *sufficient*. The dimensions capture failure
modes the team has seen before; they don't predict failure modes
specific to this change.

After the structured pass, spend a minute on:

- **What is novel about this change** that the dimensions above
  don't cover?
- **What could break that no Verified row catches?**

Surface those in the **Risks** table of the report, not as a
"feels fine" footnote. A `Ready` verdict that doesn't name a single
risk for a non-trivial change is itself a red flag.

## Process

### 1. Identify the claimed scope

Summarise what the implementation claims to do. One paragraph max.
This is the spec the report is checking against.

### 2. Compare against requirements

Map the task artifact / acceptance criteria to evidence in code and
tests. What is supported by tests? What only by code reading? What
is unverified?

### 3. Inspect risk areas

Focus on changed boundaries:

- API contracts — does `api/docs/openapi.json` still match the code?
- DB writes — migration order safe? backfill?
- Auth / authorization
- External integrations (LLM proxy, email provider)
- User-visible flows
- Async / background work
- Error paths

### 4. Verify tests and commands

Run what can be run. Record what actually ran:

| Command | Outcome |
|---|---|
| `pytest` | Pass count / fail count / not run |
| `pnpm test` | Pass count / fail count / not run |
| `pnpm lint` / `pnpm typecheck` | Clean / errors / not run |
| `ruff check .` | Clean / errors / not run |
| Browser walk (manual checklist sections) | Which sections / not done |
| PR CI | Green / red / Skipped expected per `paths` filters |

If a command was not run, **state that explicitly**. Don't claim
verification that wasn't performed.

### 5. Produce a readiness verdict

| Verdict | When to use |
|---|---|
| **Ready** | No blocking issues; tests cover the changed behaviour; verification commands ran and were green. |
| **Ready with caveats** | Minor risks remain — listed and acceptable. No blocking issues. |
| **Not ready** | At least one blocking correctness / security / test-coverage / operational issue. Named clearly with what would unblock. |

## Evidence discipline

See [`_shared/evidence-discipline.md`](../_shared/evidence-discipline.md)
— the same rules apply across `notebook-qa`, this skill, and
`notebook-pr-review`. The verdict is only useful when it's grounded
in observations: don't rubber-stamp, don't invent commands you
didn't run, distinguish evidence from inference, concrete findings
beat vague concerns, name what's good, state blockers clearly.

## Output template

```markdown
# Quality analysis: <change name>

## Verdict
<Ready | Ready with caveats | Not ready>

## Summary
<2–3 sentences: what was implemented, overall assessment, gating
finding if any.>

## Verified (evidence)
- <command run + outcome>
- <CI check + status>
- <scenario walked + result>

## Unverified (state explicitly)
- <claim that wasn't checked + why (out of scope / no access / out
  of time)>

## Issues

### Critical
- <Issue, file:line, why it blocks>

### Important
- <Issue, file:line, what would unblock>

### Minor
- <Non-blocking improvement>

## Test coverage

**Covered:**
- <behaviour with test evidence>

**Missing or weak:**
- <untested behaviour, what test would close it>

## Risks

| Risk | Impact | Mitigation / next step |
|---|---:|---|
| <risk> | High/Med/Low | <action> |

## Recommended next actions
1. <Most important fix or verification>
2. <Next>
3. <Next>
```

## Red flags

- **"Looks good to me" without listing what was actually run.** That's
  a rubber-stamp. State commands and observed output.
- **"Tests pass" with no test output quoted or paraphrased.** If you
  ran tests, paste / paraphrase the summary line; if you didn't,
  say "not run".
- **`Ready` verdict with unresolved CI red.** A `Skipped` is fine
  per `paths` filters; a `Failure` blocks `Ready`.
- **Skipping the `auth.md` §6 OTP-in-prod check for an auth
  change.** Defence-in-depth — locked by a test, verify the test
  exists.
- **Claiming OpenAPI snapshot is fresh without running
  `python scripts/openapi.py bump --dry-run`** (or relying on PR
  CI's drift check).
- **`Not ready` with vague blockers.** Name the blocker and the
  specific unblock action.

## Verification

Before publishing the readiness report:

- [ ] All quality dimensions walked (or explicitly skipped with reason)
- [ ] Every claim in "Verified" maps to an actual run command or
      observed check
- [ ] Every issue has a severity (Critical / Important / Minor)
- [ ] Verdict is one of `Ready` / `Ready with caveats` / `Not ready`
- [ ] If `Ready` — verification commands all ran green
- [ ] If `Not ready` — every blocker has a clear unblock action
- [ ] What was *not* verified is stated, not hidden

## Related

**Primary** (load alongside this skill):

- [`_shared/evidence-discipline.md`](../_shared/evidence-discipline.md)
  — what counts as evidence in a readiness report
- [`notebook-qa/references/manual-test-checklist.md`](../notebook-qa/references/manual-test-checklist.md)
  — browser-side scenarios (shared resource)
- `AGENTS.md` §11 (mandatory rules, secrets) and §12 (source of
  truth — code beats stale docs)

**Secondary** (load only when the sub-topic comes up):

- [`notebook-qa`](../notebook-qa/SKILL.md) — design side; load if
  the readiness check reveals a test design gap
- [`notebook-pr-review`](../notebook-pr-review/SKILL.md) — load at
  PR review time, not here
- `docs/qa-plan.md` §6 — scenario catalogue (when mapping coverage)
- `.agents/skills/notebook-llm/SKILL.md` — when the change touches
  the LLM proxy / WASM tier / provider chain (extra verification
  axis: secret leakage, rate limit, fallback UX)
