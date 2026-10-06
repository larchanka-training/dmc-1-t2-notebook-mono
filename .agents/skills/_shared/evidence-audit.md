# Evidence audit — shared review contract

Status: **Limited experiment** (Skill Evolution v2).
Observation period: 4–6 weeks, or at least 5 applicable PRs if that provides meaningful evidence sooner.
Do not automatically promote this experiment to permanent/accepted status without explicit owner review and decision.

Shared reference loaded alongside `evidence-discipline.md` by `notebook-pr-review` and `notebook-quality-analysis`. Applies when assessing high-impact operational, security, or reliability claims.

## Core contract

> **Claim strength must not exceed evidence strength.**

The verdict or readiness claim is valid only to the extent that it is backed by traceable, observable evidence. High-impact operational and reliability claims must explicitly delineate their evidence boundaries and remaining verification gaps.

## Five fields for a contested claim

For high-impact operational and reliability claims, record:

| Claim | Evidence | Coverage | Boundary | Gap |
|---|---|---|---|---|

- **Claim:** A concrete statement: the system does X under condition Y, or resource Z is deleted/revoked.
- **Evidence:** A traceable source: code, automated test output, CI log, runtime probe, or external confirmation, with date and scope.
- **Coverage:** The branches, environments, time window, and failure modes actually exercised.
- **Boundary:** What the evidence does not establish: local versus production, point-in-time versus continuous, repository versus cloud/host, code path versus runtime state.
- **Gap:** The observation, negative test, or independent check needed to close the gap, and who can perform it when.

## Assessment rules & evidence boundaries

Explicitly distinguish:

- **Point-in-time checks vs continuous observation:** A green health probe establishes status at the single moment of the probe, not continuous availability or `100% uptime` over an observation window.
- **Repository state vs host state vs provider/IAM state:** Removing secrets from a repository or workflow file does not prove host `.env.prod` was cleaned or external cloud IAM access keys were revoked.
- **Successful deployments vs continuous availability:** A successful deployment pipeline run or container start confirms deployment completion, not sustained operational availability.
- **Existence of a script/runbook vs successful execution of an operational drill:** The delivery and merging of backup/restore tooling or a drill runbook does not satisfy an operational verification gate until the drill is physically executed and verified on the target host.
- **Tracker/issue state vs actual operational completion:** Closing an issue or checking a task tracker item does not establish operational completion without verifiable runtime evidence.

### Quantitative claims

Quantitative claims such as `0`, `100%`, percentages, averages, error counts, or resource utilization require:
1. An enumerable, traceable evidence source (e.g. structured logs, metric counters, or automated audit outputs).
2. An explicit observation period and sample size.

Vague assertions (e.g. "zero downtime", "no errors observed", "full recovery") without bounded timestamps and log evidence must be rejected or narrowed to what was directly observed.

### Negative claims & unverified invariants

- For negative claims (e.g. no residual state, no leaked secrets, fail-closed teardown), seek negative scenarios, interrupt tests, or mutation evidence.
- If access or environment is unavailable, mark the claim `unverified` and record the gap.
- An unverified critical operational invariant blocks unconditional `Ready` or `Approve`. Documentation-only changes may proceed to `Ready` only if the unverified operational property is explicitly kept `Pending`/`In progress` rather than claimed as completed.

## Experiment protocol

This is a **limited experiment** subject to the following protocol:

- **Observation period:** 4–6 weeks, or at least 5 applicable PRs if evidence accumulates sooner.
- **Per-PR telemetry:** For every applicable PR evaluated under this pass, record:
  1. Which review pack was triggered (`notebook-pr-review` or `notebook-quality-analysis`).
  2. Claims and invariants checked.
  3. Findings discovered before merge.
  4. Later independent-review corrections.
  5. False positives or unnecessary checks.
  6. Verification gaps.
  7. Outcome: `helped`, `neutral`, `harmful`, or `insufficient evidence`.
- **Promotion policy:** Do not automatically promote the experiment to permanent or accepted status. Merging or retaining this file requires explicit owner evaluation.
- **Rollback criteria:** Revert this experiment if it produces excessive false positives, stalls low-risk changes, or fails its evaluation criteria.

## Baseline evidence cases

The following historical PRs serve as reference/replay cases for designing and evaluating this experiment:

- **PR #235:** Production health and protocol validation (curl flags, status codes, container readiness).
- **PR #237:** Backup/restore and recovery tooling (disposable DB isolation, row count verification).
- **PR #244:** Operational completion and status boundaries (runbook existence vs live execution).
- **PR #245:** Repository vs host/provider credential cleanup (workflow deprecation vs cloud IAM revocation).
- **PR #248:** Unsupported continuous/quantitative telemetry claims (point-in-time probe vs observation period).
- **PR #249:** Tooling completion vs operational activation (cron scheduling gates).
- **PR #250:** Recovery runbook safety and evidence corrections (signal traps, plaintext purge on failure).

*Note: Historical artifacts are immutable references and must not be modified.*

## Held-out control cases

To ensure the new rules remain lightweight and avoid review fatigue, the Operations / Recovery pass must **not** trigger on:

- Submodule pointer-only PRs (e.g. bumping `api/` or `ui/`).
- Dependabot workflow or dependency bumps.
- Typo-only or link-only documentation edits.
- Ordinary API or UI feature work without an operations, infrastructure, or recovery surface.

A **held-out case** is a control case not used to design the rule; it verifies that the rule does not introduce false positives or impose irrelevant claim matrices on everyday changes.

## Cross-links

- [`_shared/evidence-discipline.md`](./evidence-discipline.md) — foundational evidence discipline rules
- [`notebook-pr-review/SKILL.md`](../notebook-pr-review/SKILL.md) — reviewer-side Operations / Recovery pass
- [`notebook-quality-analysis/SKILL.md`](../notebook-quality-analysis/SKILL.md) — author-side operational invariant / claim matrix
