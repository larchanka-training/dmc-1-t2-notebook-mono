# Skill Evolution v2 — Experiment Telemetry Log

Status: **Active Experiment Ledger**
Experiment: Skill Evolution v2 (Evidence Audit & Risk-Triggered Operations / Recovery Review Pass)
Repository: `larchanka-training/dmc-1-t2-notebook-mono`
Start Date: Set upon merge of PR #252
Evaluation Horizon: 4–6 weeks post-merge (minimum 4 weeks required before closeout)
Minimum Sample Size: $\ge 5$ applicable operational PRs
Canonical Protocol: [`.agents/skills/_shared/evidence-audit.md`](../../.agents/skills/_shared/evidence-audit.md)

---

## 1. Governance & Update Lifecycle

To ensure telemetry is reliably accumulated and reproducible:

1. **Author Initialization (`notebook-quality-analysis`):**
   When authoring a PR with an operational risk surface, the author adds a new entry to the table below, filling in: `Date`, `PR / SHA`, `Trigger Reason`, and `Claims & Invariants Checked`.
2. **Reviewer Audit (`notebook-pr-review`):**
   The independent reviewer audits the claims, records any pre-merge findings in `Pre-Merge Findings`, notes remaining `Gaps`, and records estimated review latency overhead in `Review Overhead`.
3. **Reconciliation & Closeout (`$evolve-ai-instructions`):**
   During weekly maintenance cycles or upon operational deployment, the repository maintainer updates `Late Corrections` (findings discovered after merge), `False Positives` (irrelevant or incorrect findings), and assigns the row `Outcome` (`helped`, `neutral`, `harmful`, or `insufficient evidence`).

---

## 2. Measurable Evaluation Criteria

At the evaluation horizon (4–6 weeks post-merge), the repository owner evaluates the accumulated ledger using the following explicit criteria:

| Outcome | Quantitative & Qualitative Thresholds |
|---|---|
| **`accepted`** | - Sample size $\ge 5$ applicable operational PRs evaluated across $\ge 4$ weeks.<br>- $\ge 1$ high-impact operational/recovery defect caught before merge that would have escaped standard review.<br>- **0** blocking false positives on held-out control cases.<br>- False-positive rate on applicable PRs $\le 10\%$.<br>- Review latency overhead acceptable ($\le 15$ minutes per applicable PR).<br>- Independent repository owner review confirms efficacy. |
| **`revise`** | - Discovers valid findings, but reveals operational friction: e.g. triggers too broad/narrow, or checklist overhead excessive, indicating the need to extract checks into a dedicated reference file or refine N/A rules. |
| **`rejected`** | - High false-positive rate ($> 20\%$ of findings are false alarms or irrelevant).<br>- Stalls low-risk development or causes severe review fatigue.<br>- Misses a critical operational defect with a clear reproducer that should have been caught. |
| **`insufficient evidence`** | - Fewer than 5 applicable operational PRs evaluated within the 6-week window, or lack of independent re-review verification data.<br>*(Mandates extending the observation window or closing the experiment without permanent adoption).* |

---

## 3. Operational Telemetry Ledger

| Date | PR / SHA | Trigger Reason | Claims / Invariants Checked | Pre-Merge Findings | Late Corrections | False Positives | Gaps | Review Overhead | Outcome |
|---|---|---|---|---|---|---|---|---|---|
| *Pending* | PR #... (`...`) | *e.g. Deploy config* | *e.g. Fail-closed exit on Liquibase error* | *e.g. Caught missing non-zero trap* | *e.g. None* | *e.g. 0* | *e.g. Production drill pending* | *e.g. 10m* | *helped* |

*New entries will be appended above during the 4–6 week observation window.*

---

## 4. Baseline Replay Reference Cases (Historical Controls)

These historical PRs serve as frozen baseline controls for verifying review expectations:

| Historical PR | Risk Category | Expected Trigger & Checks | Historical Findings Addressed |
|---|---|---|---|
| `larchanka-training/dmc-1-t2-notebook-mono#235` | Health & Protocol Validation | Readiness probe, curl flags, status codes | Caught missing error body inspection, clarified readiness vs liveness contracts |
| `larchanka-training/dmc-1-t2-notebook-mono#237` | Backup / Restore Recovery | Disposable DB isolation, row count verification | Prevented mutation of live production DB, enforced disposable target isolation |
| `larchanka-training/dmc-1-t2-notebook-mono#244` | Operational Completion | Tooling vs operational drill execution | Prevented false closure of live operational migration gates |
| `larchanka-training/dmc-1-t2-notebook-mono#245` | Credential Lifecycle | Repository vs host `.env.prod` vs cloud IAM | Delineated repo secret removal from actual cloud IAM access key revocation |
| `larchanka-training/dmc-1-t2-notebook-mono#248` | Telemetry & Observability | Point-in-time check vs continuous observation | Eliminated unsupported 100% uptime claims from single health probe |
| `larchanka-training/dmc-1-t2-notebook-mono#249` | Tooling vs Operational Activation | Automation script vs cron scheduling | Prevented conflation of script availability with live scheduler activation |
| `larchanka-training/dmc-1-t2-notebook-mono#250` | Recovery Runbook Safety | Plaintext lifecycle, signal traps, error exit | Enforced non-zero exit on SIGINT/SIGTERM, ensured plaintext dump purge on error |
