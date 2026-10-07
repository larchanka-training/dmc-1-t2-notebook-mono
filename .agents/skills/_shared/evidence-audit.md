# Evidence audit — shared review contract

Status: **Limited experiment** (Skill Evolution v2).
Observation period: 4–6 weeks post-merge (minimum 4 weeks required; minimum sample size: 5 applicable operational PRs).
Persistent ledger: [`docs/experiments/skill-evolution-v2-log.md`](../../../docs/experiments/skill-evolution-v2-log.md).
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
- **Existence of a script/runbook vs successful execution of an operational drill:** The delivery and merging of backup/restore tooling or a drill runbook does not satisfy an operational verification gate until the drill is physically executed and verified in the environment designated by the runbook (e.g. an isolated off-host disposable workstation, without mutating production).
- **Tracker/issue state vs actual operational completion:** Closing an issue or checking a task tracker item does not establish operational completion without verifiable runtime evidence.

### Quantitative claims

Quantitative claims such as `0`, `100%`, percentages, averages, error counts, or resource utilization require:
1. An enumerable, traceable evidence source (e.g. structured logs, metric counters, or automated audit outputs).
2. An explicit observation period and sample size.

Vague assertions (e.g. "zero downtime", "no errors observed", "full recovery") without bounded timestamps and log evidence must be rejected or narrowed to what was directly observed.

### Negative claims, unverified invariants & applicability

- **Negative claims:** For negative claims (e.g. no residual state, no leaked secrets, fail-closed teardown), seek negative scenarios, interrupt tests, or mutation evidence.
- **Unverified invariants:** If access or environment is unavailable, mark the claim `unverified` and record the gap. An unverified critical operational invariant blocks unconditional `Ready` or `Approve`. Documentation-only changes may proceed to `Ready` only if the unverified operational property is explicitly kept `Pending`/`In progress` rather than claimed as completed.
- **Applicability & N/A:** Checks must be scoped to the specific operational risk surface of the PR. If a check does not apply (for example, encrypted dump lifecycle or signal traps on a credential cleanup or monitoring PR), mark it `N/A` with a brief 1-sentence rationale. Do not run irrelevant checks or invent fictitious failure paths.

## Semantic risk triage for exclusions

A positive operational risk trigger **always takes precedence** over a mechanical PR category:

1. **Submodule pointer bumps (`api/`, `ui/`):**
   - Check what commits are pulled in. If the submodule bump includes database migrations (Liquibase), auth/secret contract modifications, or API deployment configuration, the Operations / Recovery pass triggers.
   - If the submodule bump was already independently reviewed in the submodule repository and introduces no new monorepo operational risk, cite the submodule review evidence rather than re-running a redundant full pass.
2. **Dependabot PRs:**
   - If Dependabot updates GitHub Actions workflows (e.g. actions used in `deploy-aeza-production.yml` or `ghcr-publish.yml`) or the Docker proxy / base container images, the Operations / Recovery pass triggers to verify fail-closed behavior, security pinning, and deployment consistency.
   - If Dependabot only updates routine test/dev dependencies with no production runtime surface, the heavy pass is skipped.
3. **Pure held-out exclusions (always skip):**
   - Typo-only or link-only documentation edits.
   - Pure UI styling or non-operational frontend components without deployment or runtime configuration changes.

A **held-out case** is a control case not used to design the rule; it verifies that the rule does not introduce false positives or impose irrelevant claim matrices on everyday changes.

## Experiment protocol & persistent telemetry

This is a **limited experiment** subject to the following protocol:

- **Observation period:** 4–6 weeks post-merge. Minimum sample size is **5 applicable operational PRs**. The observation period cannot be closed earlier than 4 weeks even if 5 PRs are reached, to allow observation of late independent-review corrections.
- **Persistent ledger:** All applicable PRs are recorded in [`docs/experiments/skill-evolution-v2-log.md`](../../../docs/experiments/skill-evolution-v2-log.md).
- **Update lifecycle:**
  1. *Author (`notebook-quality-analysis`):* Appends new row with PR/SHA, trigger reason, and claims checked.
  2. *Reviewer (`notebook-pr-review`):* Records pre-merge findings, verification gaps, and estimated review latency overhead.
  3. *Maintainer (`$evolve-ai-instructions`):* Reconciles late corrections, false positives, and assigns row outcome.
- **Review overhead metric:** Record estimated review latency overhead (target: $\le 15$ minutes per applicable PR).
- **Measurable decision criteria (Four Outcomes):**
  - **`accepted`:** Sample size $\ge 5$ applicable PRs across $\ge 4$ weeks; $\ge 1$ genuine operational defect caught before merge; 0 false-positive blocking findings on held-out cases; false-positive rate on applicable PRs $\le 10\%$; review overhead acceptable ($\le 15$ min per PR); confirmed by owner.
  - **`revise`:** Discovers valid findings, but triggers are too broad/narrow or checklist overhead indicates need to extract into a dedicated reference file or refine N/A rules.
  - **`rejected`:** High false-positive rate ($> 20\%$); stalls low-risk work; or misses a reproducible critical operational defect.
  - **`insufficient evidence`:** Fewer than 5 applicable operational PRs evaluated in the 6-week window, or lack of post-merge verification data. (Mandates extending observation or closing without permanent adoption).

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

## Cross-links

- [`_shared/evidence-discipline.md`](./evidence-discipline.md) — foundational evidence discipline rules
- [`notebook-pr-review/SKILL.md`](../notebook-pr-review/SKILL.md) — reviewer-side Operations / Recovery pass
- [`notebook-quality-analysis/SKILL.md`](../notebook-quality-analysis/SKILL.md) — author-side operational invariant / claim matrix
- [`docs/experiments/skill-evolution-v2-log.md`](../../../docs/experiments/skill-evolution-v2-log.md) — experiment telemetry ledger
