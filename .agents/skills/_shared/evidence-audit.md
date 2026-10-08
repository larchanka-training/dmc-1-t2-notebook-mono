# Evidence audit — shared review contract

Status: **Limited experiment** (Skill Evolution v2).
Observation period: 4–6 weeks post-merge (minimum 4 weeks required; minimum sample size: 5 applicable operational PRs and 4 observed held-out control PRs).
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

A **held-out case** is a control case not used to design the rule; it verifies that the rule does not introduce false positives or impose irrelevant claim matrices on everyday changes. Missing observations must not be counted as successful control cases.

## Experiment protocol & evaluation metrics

This is a **limited experiment** subject to the following protocol:

- **Observation period:** 4–6 weeks post-merge. Minimum sample size is **5 applicable operational PRs** and **4 observed held-out control PRs** (at least one in each control category: Submodule pointer-only, Dependabot, Typo/link documentation, Ordinary API/UI). The observation period cannot be closed earlier than 4 weeks even if 5 PRs are reached, to allow observation of late independent-review corrections.
- **Persistent ledger:** All applicable operational PRs and held-out control observations are recorded in [`docs/experiments/skill-evolution-v2-log.md`](../../../docs/experiments/skill-evolution-v2-log.md).
- **Telemetry lifecycle:**
  1. *Local Collection:* Author (`notebook-quality-analysis`) and reviewer (`notebook-pr-review`) collect data locally during execution (PR/SHA, trigger, claims, findings, gaps, review overhead).
  2. *Draft Preparation:* Automated workflows (e.g. weekly `$evolve-ai-instructions` or author PR prep) generate proposed ledger entries as local draft notes. Automation does not write or commit directly to Git without authorization.
  3. *Authorized Publication:* Updating and committing `docs/experiments/skill-evolution-v2-log.md` is performed only upon explicit human maintainer authorization.

### Evaluation metrics

- **False Finding Rate (FFR):**
  $$\text{FFR} = \frac{\text{Count of false-positive or rejected findings}}{\text{Total findings generated by the pass}} \times 100\%$$
- **False Trigger Rate (FTR):**
  $$\text{FTR} = \frac{\text{Count of unique PRs where pass triggered without operational risk surface}}{\text{Total count of unique PRs for which the pass triggered}} \times 100\%$$
  *Deduplication rule:* Author runs, reviewer runs, and re-reviews on updated commits of the same PR are deduplicated and counted once per unique PR.
- **Missed Trigger Rate (MTR):**
  $$\text{MTR} = \frac{\text{Count of unique operational PRs where pass was skipped}}{\text{Total count of unique operational PRs}} \times 100\%$$
- **Zero-denominator rule:** If a denominator equals $0$, the metric value is **$\text{N/A}$** (uncomputable on available data, not zero errors). An $\text{N/A}$ value does not satisfy acceptance or revision thresholds requiring $\le 10\%$ or $\le 20\%$; promotion to `accepted` requires computable rates based on observed non-zero denominators.
- **Review latency overhead:** Estimated minutes added per applicable PR (target: $\le 15$ minutes).

### Evaluation decision order & disjoint criteria

Evaluate accumulated data strictly in the following priority order:

1. **`early rejection / critical failure` (Evaluated first, continuous):**
   - Applies immediately at any time during the observation window (without waiting for the 5-PR sample minimum or 4-week duration) if ANY of the following occur:
     - Missed a critical operational defect with a clear reproducer that was subsequently caught post-merge or in production; OR
     - $\ge 1$ blocking false positive on held-out control cases; OR
     - Review pass induced destructive actions, leaked secrets, or attempted mutation of live production environments.
   - *Outcome:* The experiment is terminated immediately and reverted; do not wait to accumulate further PRs.
2. **`insufficient evidence` (Evaluated second, sample threshold check):**
   - Applies if the experiment has not triggered early rejection, BUT sample size $< 5$ unique applicable operational PRs, OR observation duration $< 4$ weeks, OR held-out observations $< 4$ distinct PRs (at least one per control category), OR lack of independent review verification data.
   - *Outcome:* The experiment cannot be promoted or rejected; the window must be extended or closed without permanent adoption.
3. **`rejected` (Evaluated third, mature sample threshold):**
   - Applies on mature sample ($\ge 5$ operational PRs, $\ge 4$ weeks) if ANY of the following occur:
     - Computable $\text{FFR} > 20\%$, OR
     - Computable $\text{FTR} > 20\%$, OR
     - Computable $\text{MTR} > 20\%$, OR
     - Average review latency overhead $> 20$ minutes per applicable PR.
   - *Outcome:* The experiment failed its quality gates and is reverted.
4. **`accepted` (Evaluated fourth, strict promotion):**
   - Applies if ALL of the following technical conditions are met:
     - Sample size $\ge 5$ applicable operational PRs across $\ge 4$ weeks, AND
     - $\ge 1$ material operational/recovery finding independently confirmed by review before merge, AND
     - Held-out control cases $\ge 4$ distinct PRs ($\ge 1$ per control category) with 0 blocking false positives, AND
     - Computable $\text{FFR} \le 10\%$ (cannot be $\text{N/A}$), AND
     - Computable $\text{FTR} \le 10\%$ (cannot be $\text{N/A}$), AND
     - Computable $\text{MTR} \le 10\%$ (cannot be $\text{N/A}$), AND
     - Average review latency overhead $\le 15$ minutes per applicable PR.
   - *Status holding:* When all technical conditions are satisfied, the trial verdict is held as **`accepted (pending owner confirmation)`** awaiting explicit repository owner sign-off. It is **not** downgraded to `revise`. Formal promotion occurs upon explicit repository owner approval.
5. **`no demonstrated benefit` (Evaluated fifth, mature sample without material operational findings):**
   - Applies if the experiment completed a mature sample ($\ge 5$ operational PRs across $\ge 4$ weeks, $\ge 4$ controls) without triggering rejection (overhead $\le 20$ minutes, error rates $\le 20\%$, 0 blocking false positives on controls), BUT produced **0 material confirmed findings** (e.g. $\text{FFR} = \text{N/A}$ with zero findings, or all confirmed findings were purely non-material/trivial without operational or recovery risk impact).
   - *Overhead independence:* Applies for any overhead $\le 20$ minutes (including $\le 15$m and $15\text{–}20$m). A pass that produces no material findings does not warrant adoption regardless of review duration.
   - *Outcome:* Close the experiment without permanent adoption; additional operational benefit was not demonstrated on this sample.
6. **`revise` (Evaluated sixth, intermediate refinement & mature sample fallback):**
   - Applies if the experiment produced material confirmed findings, but fell into the intermediate refinement zone:
     - $10\% < \text{FFR} \le 20\%$, OR
     - $10\% < \text{FTR} \le 20\%$, OR
     - $10\% < \text{MTR} \le 20\%$, OR
     - Average review latency overhead is $15\text{–}20$ minutes per applicable PR, OR
     - The pass demonstrated material utility but requires structural adjustments (e.g. extracting checks into a separate reference file or tightening triggers).
   - Also serves as the explicit fallback verdict for any remaining mature sample ($\ge 5$ operational PRs, $\ge 4$ weeks, $\ge 4$ controls) not resolved by stages 3, 4, or 5.
   - *Outcome:* Revise triggers or structure and conduct a focused follow-up iteration.

### Boundary Validation Matrix & Completeness Guarantee

Any change to evaluation criteria must be validated against boundary scenarios across all decision axes to guarantee both mutual disjointness and complete coverage:

| Scenario / Boundary Case | Sample & Duration | Material Confirmed Findings | Error Rates (FFR / FTR / MTR) | Review Overhead | Verdict | Rationale |
|---|---|---|---|---|---|---|
| Critical defect missed with reproducer | Any (e.g. 2 PRs, 1w) | Any | Any | Any | **`early rejection`** | Stage 1: Continuous critical safety trigger halts failing experiment immediately. |
| Blocking false positive on control | Any (e.g. 3 PRs, 2w) | Any | Any | Any | **`early rejection`** | Stage 1: Zero-tolerance for false blockers on held-out controls. |
| Unsafe action (prod mutation / secret leak) | Any | Any | Any | Any | **`early rejection`** | Stage 1: Safety violation triggers immediate rollback. |
| Incomplete sample / duration | $<5$ PRs or $<4$w or $<4$ controls | Any | Any | Any | **`insufficient evidence`** | Stage 2: Cannot promote or reject without minimum observation window. |
| High review overhead | Mature ($\ge 5$ PRs, $\ge 4$w, $\ge 4$c) | Any (0 or $\ge 1$) | Any | $> 20$m (e.g. 21m) | **`rejected`** | Stage 3: Excessive review cost exceeds rejection threshold. |
| High error rate | Mature | Any | Any $> 20\%$ | Any | **`rejected`** | Stage 3: False positive, false trigger, or missed trigger rate exceeds threshold. |
| Zero findings, low overhead | Mature | 0 ($\text{FFR} = \text{N/A}$) | $\le 10\%$ (or $\text{N/A}$) | $\le 15$m (e.g. 10m, 15m) | **`no demonstrated benefit`** | Stage 5: No material defects caught; extra pass added no demonstrated value. |
| Zero findings, intermediate overhead | Mature | 0 ($\text{FFR} = \text{N/A}$) | $\le 10\%$ (or $\text{N/A}$) | $15 < \text{overhead} \le 20$m (e.g. 16m, 20m) | **`no demonstrated benefit`** | Stage 5: No material defects caught; additional overhead confirms pass is not worth keeping. |
| Non-material findings only | Mature | 0 material (cosmetic only) | $\le 10\%$ | $\le 20$m | **`no demonstrated benefit`** | Stage 5: Trivial/cosmetic findings do not justify operational review pass. |
| Clean pass, low overhead | Mature | $\ge 1$ material confirmed | All computable $\le 10\%$ | $\le 15$m (e.g. 12m, 15m) | **`accepted`** | Stage 4: Meets all quality, finding, and latency thresholds (with owner sign-off). |
| Material finding, intermediate overhead | Mature | $\ge 1$ material confirmed | All computable $\le 10\%$ | $15 < \text{overhead} \le 20$m (e.g. 16m, 20m) | **`revise`** | Stage 6: Useful finding confirmed, but review overhead requires trigger tuning. |
| Material finding, intermediate error rate | Mature | $\ge 1$ material confirmed | $10\% < \text{rate} \le 20\%$ | $\le 15$m | **`revise`** | Stage 6: Useful finding confirmed, but error rates require trigger refinement. |

## Baseline evidence cases (Historical controls)

These historical PRs serve as frozen baseline references for designing the checks. They are historical references only; expected detections were not replayed during this experiment:

- **PR #235:** Production health and protocol validation (readiness probe, curl flags, status codes). Historical finding; expected detection not replayed.
- **PR #237:** Backup/restore and recovery tooling (disposable DB isolation, row count verification). Historical finding; expected detection not replayed.
- **PR #244:** Operational completion and status boundaries (tooling vs operational drill execution). Historical finding; expected detection not replayed.
- **PR #245:** Repository vs host/provider credential cleanup (repository vs host `.env.prod` vs cloud IAM). Historical finding; expected detection not replayed.
- **PR #248:** Unsupported continuous/quantitative telemetry claims (point-in-time check vs continuous observation). Historical finding; expected detection not replayed.
- **PR #249:** Tooling completion vs operational activation (automation script vs cron scheduling). Historical finding; expected detection not replayed.
- **PR #250:** Recovery runbook safety and evidence corrections (plaintext lifecycle, signal traps, error exit). Historical finding; expected detection not replayed.

*Note: Historical artifacts are immutable references and must not be modified.*

## Cross-links

- [`_shared/evidence-discipline.md`](./evidence-discipline.md) — foundational evidence discipline rules
- [`notebook-pr-review/SKILL.md`](../notebook-pr-review/SKILL.md) — reviewer-side Operations / Recovery pass
- [`notebook-quality-analysis/SKILL.md`](../notebook-quality-analysis/SKILL.md) — author-side operational invariant / claim matrix
- [`docs/experiments/skill-evolution-v2-log.md`](../../../docs/experiments/skill-evolution-v2-log.md) — experiment telemetry ledger
