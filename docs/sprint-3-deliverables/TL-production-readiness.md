# Sprint 3 Tech Lead — Production Readiness

> Date: **2026-06-27**. Derived from the prioritized roadmap
> (`.agents/issues/TODO/project-roadmap-todo.md`), which was built from
> **closed** issues, the `mono`/`ui`/`api` git history and a live check of the
> production domain — not only open tickets.
>
> Issue references use the full `owner/repo#NN` form. Repos: `js-notebook` =
> `larchanka-training/js-notebook` (the central tracker, where most issues
> live), `mono`/`ui`/`api` = `dmc-1-t2-notebook-(mono|ui|api)`.

## Objective

Assess the technical readiness of JS Notebook for launch and identify the most important engineering risks.

## Scope

- architecture and system behavior
- operational readiness
- release blockers and likely failure points
- medium-term engineering priorities

## Questions To Answer

### 1. What will break first?

- System area: **OTP email delivery (sign-in path).**
- Failure mode: a single delivery provider (Resend) is the only channel for the
  one-time code. If it throttles, errors or has an outage, **no one can sign
  in** — and sign-in is required to sync notebooks.
- Why this is the most likely early failure: it is the one external dependency
  on the critical path with no fallback today; everything else (execution,
  notebook CRUD, local autosave) degrades gracefully offline, auth does not.
- User impact: complete lockout of new sessions and of sync for existing users
  until delivery recovers.
- Evidence: SES fallback is an explicit P0 epic still in progress —
  `larchanka-training/dmc-1-t2-notebook-mono#124` (42%); the OTP rate-limit
  `count + insert` race and the burn-the-OTP trade-off are already documented as
  known limitations.
- Runner-up: an unprotected production node without container CPU/RAM limits —
  `larchanka-training/js-notebook#93` — a heavy/abusive run can starve the box.

### 2. What technical debt exists?

| Area | Debt | Why it exists | Risk | Suggested action |
|---|---|---|---|---|
| Auth delivery | OTP delivery has no fallback; rate-limit `count + insert` race; burn-the-OTP trade-off | Shipped MVP-first on a single provider (Resend) | High — sign-in lockout | Land SES fallback `larchanka-training/dmc-1-t2-notebook-mono#124` |
| Frontend perf | Main JS `~7.93 MB` served without gzip/brotli; cold FCP `4 856 ms` | Compression/code-split deferred to ship features | Medium — slow/unusable first load on weak networks | gzip/brotli, immutable cache headers, code-split WebLLM, shrink favicon (`docs/sprint-3-deliverables/E3-performance-report.md` §10) |
| Execution | Backend `/execute` path not wired in prod; QuickJS browser-only | Hybrid execution is the target, MVP is browser | Medium — heavy runs stay client-side | `dmc-1-t2-notebook-ui#59/#60` + env in `dmc-1-t2-notebook-mono#103` |
| Prod node | No Docker CPU/GPU/RAM limits | Not set during initial bring-up | Medium — one run starves the node | `larchanka-training/js-notebook#93` |
| AI correctness | LLM context ignores QuickJS / web-worker / notebook limits | Context builder shipped before limit-awareness | Medium — wrong/oversized generations | `larchanka-training/js-notebook#168` |
| Sync | Foreground pull of others' changes (#137) and trusted-device UX (#136) not finished | Sync core (#131–#135) shipped first | Low-Medium — stale view, device-trust gaps | Finish `larchanka-training/js-notebook#137` and `#136` |
| First-create durability | Content + sync-marker not written in one IndexedDB tx (liveness gap, self-healing) | Edge case found after core sync | Low — no data loss today | Atomic write follow-up of #135 (draft in `.agents/issues/TARDIS-130/`) |
| Docs drift | Roadmap board status lags real issue state (e.g. `ui#77`, `mono#140`, `mono#154` closed but not in "Done") | Manual board upkeep | Low — planning confusion | Reconcile the t2 board with `is:open` per repo |

### 3. What are the release risks?

| Risk | Severity | Likelihood | Detection | Mitigation | Owner |
|---|---|---|---|---|---|
| OTP delivery outage → sign-in lockout | High | Medium | Prod smoke of OTP delivery; delivery-provider alerts | SES fallback `larchanka-training/dmc-1-t2-notebook-mono#124`; manual IAM/kill switches | Backend / DevOps |
| Cold load too slow on weak networks | Medium | High | `E3-performance-report.md` baseline (FCP `4 856 ms`, `~7.93 MB` JS) | gzip/brotli + cache headers + code-split | Frontend |
| Prod node starved by heavy/abusive run | Medium | Medium | CloudWatch CPU/mem; circuit breaker | Docker CPU/RAM limits `larchanka-training/js-notebook#93` | DevOps |
| Wrong/oversized AI generations | Medium | Medium | AI QA suite; user reports | Limit-aware context `larchanka-training/js-notebook#168` | Backend |
| Release certification not complete | High | Low | `larchanka-training/js-notebook#157` gated on audits | Finish Security `#155` + Tech `#159` audits | QA / Tech Lead |
| Bedrock budget overrun | Medium | Low | Cost alarms; usage metrics | IAM-revoke kill switch today; env flag `dmc-1-t2-notebook-api#74` | DevOps / Backend |

### 4. What should be done in the next 3 months?

Priorities mirror the roadmap (`P0` release blocker → `P3` large/needs design).

| Priority | Initiative | Why now | Expected outcome | Rough effort |
|---|---|---|---|---|
| P0 | SES OTP fallback (`larchanka-training/dmc-1-t2-notebook-mono#124`, steps `#125`–`#132`) | Sign-in single point of failure | Reliable OTP delivery, no lockout | M (multi-step epic) |
| P0 | Release Certification (`larchanka-training/js-notebook#157`) after Security `#155` + Tech `#159` audits | Can't release without it | Signed Go/No-Go | M |
| P0 | AI context limits bugfix (`larchanka-training/js-notebook#168`) | Affects AI correctness | Generations respect runtime/notebook caps | S |
| P0 | Docker CPU/RAM limits (`larchanka-training/js-notebook#93`) | Prod node protection | Stable node under load | S |
| P1 | Finish sync: foreground pull `#137`, trusted-device `#136` | Core sync (#131–#135) already done | Live multi-device sync, closes epic `#130` | M |
| P1 | Backend `/execute` (`dmc-1-t2-notebook-ui#59`/`#60`) + env in `dmc-1-t2-notebook-mono#103` | Hybrid execution target | Heavy runs routed to backend | M |
| P1 | Operational levers: kill-switch `dmc-1-t2-notebook-api#74`, user block `#73`; export `dmc-1-t2-notebook-ui#82`; domain follow-ups `dmc-1-t2-notebook-mono#147` | Reliability/moderation/ops | Safer, more controllable prod | M |
| P2 | User settings + passkey (WebAuthn) — unblocked by the live domain | Domain `jsnb.org` is live | Passwordless login + preferences | M (no ticket yet) |
| P2 | `fetch` in sandbox; Vega + animated charts in output | Educational value, low coupling | Richer notebooks | M (drafts ready) |
| P3 | Functional dashboard → versioning → sharing | Shared data-model foundation | Product depth | L — needs design + T3 backend persistence |

## Current Readiness Snapshot

| Area | Status | Notes |
|---|---|---|
| Product stability | 🟢 Good | Core flows (notebook, execution, local autosave, sync core #131–#135) shipped; `https://jsnb.org` live (verified 2026-06-27) |
| Security | 🟡 Conditional | Review done (XSS/JWT/authz/sandbox/prompt injection); findings mitigated; audit `larchanka-training/js-notebook#155` gating cert |
| Performance | 🟡 At risk | Backend p95 stable; cold first-load is the bottleneck (FCP `4 856 ms`, `~7.93 MB` JS, no gzip/brotli) |
| Observability | 🟢 Good | CloudWatch analytics + alarms; metadata-only logging (no code/prompts/tokens) |
| Cost control | 🟢 Good | Cost model done (`E2-cost-analysis.md`); Bedrock kill switches available |
| Recovery readiness | 🟢 Good | DR runbook landed (`dmc-1-t2-notebook-mono#154`); plan `larchanka-training/js-notebook#158` in review |
| Test coverage | 🟡 Conditional | Regression in progress; Release Certification `larchanka-training/js-notebook#157` not yet signed |
| Documentation | 🟢 Good | `/docs` canonical English; contracts (OpenAPI, `auth.md`) tracked; board status lags real issue state |

## Top Findings

1. **OTP delivery is the single point of failure.** No fallback channel; an
   outage means a full sign-in lockout. SES fallback
   (`larchanka-training/dmc-1-t2-notebook-mono#124`) is the top P0.
2. **The first bottleneck is the frontend cold load, not the backend.** Backend
   p95 is healthy; cold FCP `4 856 ms` and `~7.93 MB` of uncompressed JS are the
   real user-facing risk — cheap wins available (gzip/brotli, cache headers,
   code-split).
3. **Release is gated on certification + two audits.** Security
   `larchanka-training/js-notebook#155` and Tech `#159` audits must finish
   before Release Certification `#157` can be signed.

## Recommended Decision

- Recommendation: **conditional Go.** The product is live and core flows are
  stable; ship once the conditions below are met. (Final Go/No-Go is owned by
  the QA release certification, `docs/sprint-3-deliverables/QA-release-report.md`.)
- Conditions before release:
  - SES OTP fallback delivered and prod-smoke verified
    (`larchanka-training/dmc-1-t2-notebook-mono#124`);
  - Security `#155` + Tech `#159` audits complete and Release Certification
    `#157` signed;
  - AI context-limit bugfix (`larchanka-training/js-notebook#168`) and Docker
    CPU/RAM limits (`#93`) landed.
- Conditions acceptable as post-release follow-up:
  - frontend compression/code-split (perf, `E3-performance-report.md` §10);
  - foreground pull `#137` and trusted-device UX `#136`;
  - backend `/execute` rollout (`dmc-1-t2-notebook-ui#59`/`#60`,
    `dmc-1-t2-notebook-mono#103`);
  - first-create durability atomic-write follow-up.

## Evidence

- Code / infra references: `.agents/issues/TODO/project-roadmap-todo.md`
  (2026-06-27); live prod `https://jsnb.org` (verified); CI/CD in
  `.github/workflows/`; AWS stack in `terraform/`.
- Test or audit references: `docs/sprint-3-deliverables/E3-performance-report.md`
  (perf baseline, issue `larchanka-training/js-notebook#154`),
  `E4-security-review.md`, `E2-cost-analysis.md`, `DevOps-runbook.md`
  (`dmc-1-t2-notebook-mono#154`); Release Certification
  `larchanka-training/js-notebook#157`.
- Open questions:
  - Is the release already past? If so, P0/P1 execution/sync items move up.
  - Cross-team dependency: versioning/sharing/export rely on T3 backend
    persistence (`larchanka-training/js-notebook#146`/`#127`/`#149`/`#53`) —
    must be synced before starting.
