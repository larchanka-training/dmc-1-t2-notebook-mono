# Aeza Production Post-Cutover Verified Events & Health Summary

**Document ID:** `DOC-OPS-AEZA-OBS-20260924`
**Date:** 2026-09-24
**Scope:** Aeza Production Host (`jsnotes-production` on `https://jsnb.org`)
**Target Milestone:** Phase G Observation Tracking ([`aeza-migration-implementation-plan.md`](./aeza-migration-implementation-plan.md) §Phase G, items 190 & 246)
**Status:** In Progress (Interim Verified Events Summary)

---

## 1. Executive Summary

Production traffic, database storage, Cloudflare origin proxying, and authentication were cut over from Beget to Aeza on **2026-09-13**. Following cutover, the application stack entered the mandatory **Phase G Observation Window**.

This document records factual deployment milestones, health check verifications, and operational events captured between cutover (2026-09-13) and the deployment of Monorepo PR #247 on **2026-09-24 12:17 UTC**:
- **Continuous Service Operations:** Zero severity-1 or severity-2 outages or data-loss incidents were reported on the Aeza production environment (`https://jsnb.org`).
- **Verified Deployment Workflows:** Multiple automated deployment workflows were successfully executed, including a verified immutable rollback drill (`sha-7e81b92`, run 34936085722) and roll-forward (`sha-731ca16`, run 34936157711).
- **Beget VPS Decommissioning:** Successfully completed on 2026-09-22 after confirming zero write attempts during the observation freeze, closing tracking issue [`larchanka-training/js-notebook#187`](https://github.com/larchanka-training/js-notebook/issues/187).
- **Default LLM Provider Migration:** OpenRouter was established as the production cloud LLM provider and deployed to production via [`larchanka-training/dmc-1-t2-notebook-mono#247`](https://github.com/larchanka-training/dmc-1-t2-notebook-mono/pull/247) (run 35998023334).

**Observation Gate Status:** While verified deployment milestones and service health checks have passed without recorded incidents, full continuous time-series telemetry (e.g. continuous external latency/uptime tracking, persistent Prometheus/Grafana host metrics, Cloudflare Analytics error logs, and Resend delivery dashboards) is not integrated into an automated telemetry pipeline. Consequently, Phase G observation items 190 and 246 remain marked in-progress (`[ ]`) until formal operational telemetry attachment or owner sign-off.

---

## 2. Verified Milestone Timeline

The following timeline details verified operational events and deployment runs. These entries represent key verified milestone events rather than an exhaustive registry of every background job.

| Date / Time (UTC) | Event / Operational Milestone | Verification Reference & Mechanism | Outcome |
|---|---|---|---|
| **2026-09-13** | Initial production cutover & Cloudflare DNS repoint | [`aeza-migration-implementation-plan.md`](./aeza-migration-implementation-plan.md) §3 (manual procedure) | Write freeze on Beget verified; Aeza live |
| **2026-09-14 08:53–08:57** | First automated deploy via `deploy-aeza-production.yml` | Run 34825043090 (`workflow_run`, `sha-7e81b92`) | Pre-deploy dump, migrations, origin health check green |
| **2026-09-15 06:13–06:14** | Hardened health gates deployed | Run 34936010541 (`workflow_run`, `sha-731ca16`) | Origin `/api/v1/health` and public UI gates verified |
| **2026-09-15 06:14–06:15** | Controlled immutable rollback drill | Run 34936085722 (`workflow_dispatch`, `sha-7e81b92`) | Rollback to exact prior image tag verified |
| **2026-09-15 06:15–06:16** | Controlled roll-forward drill | Run 34936157711 (`workflow_dispatch`, `sha-731ca16`) | Clean forward deployment, zero data drift |
| **2026-09-16–18** | Beget read-only observation freeze window | Phase G observation | Zero writes received on legacy Beget DB |
| **2026-09-22 10:00** | Beget deployment workflow retired | [`larchanka-training/dmc-1-t2-notebook-mono#243`](https://github.com/larchanka-training/dmc-1-t2-notebook-mono/pull/243) | Workflow moved to `archive/beget-workflows/` |
| **2026-09-22 12:00** | Beget VPS decommissioned by owner | [`larchanka-training/js-notebook#187`](https://github.com/larchanka-training/js-notebook/issues/187) | SSH access terminated; server deleted |
| **2026-09-22 23:45** | AWS preview workflows archived; Bedrock deprecated | [`larchanka-training/dmc-1-t2-notebook-mono#245`](https://github.com/larchanka-training/dmc-1-t2-notebook-mono/pull/245) | Workflows in `archive/aws-workflows/`; 0 AWS secrets |
| **2026-09-23 17:46** | API default LLM provider switched to OpenRouter | [`larchanka-training/dmc-1-t2-notebook-api#103`](https://github.com/larchanka-training/dmc-1-t2-notebook-api/pull/103) | 375 tests green, zero-config dev preflight verified |
| **2026-09-24 12:16–12:17** | Monorepo pointer bumped & deployed to production | Run 35998023334 (`workflow_run`, `sha-4415e4d`) | `AEZA_PRODUCTION_DEPLOY_OK: sha-4415e4d` verified |

---

## 3. Verified Health & Operational Evidence

### 3.1 Container Health & Service Liveness
Production services run under Docker Compose (`-p jsnotes-production`) on the Aeza VPS:
- **`postgres` (PostgreSQL 16):** Database health check (`pg_isready -U postgres`) validated during all container startup and deployment sequences. Liquibase database migrations executed cleanly across all updates without table locks or rollback failures.
- **`api` (FastAPI backend):** Dedicated health endpoint `/api/v1/health` returned HTTP 200 with `{"status": "ok", "environment": "production"}` across all deployment verification gates. Zero unhandled 500 errors surfaced in post-deploy smoke checks.
- **`frontend` (Vite / Nginx static bundle):** Origin probes (`curl -f -s -k http://127.0.0.1/`) consistently verified presence of `<div id="root">` following each deployment.
- **`proxy` (Nginx reverse proxy with Cloudflare Origin CA):** Terminates TLS on port 443 with Cloudflare Origin Certificate; consistently serves mandatory cross-origin isolation headers (`Cross-Origin-Opener-Policy: same-origin`, `Cross-Origin-Embedder-Policy: require-corp`) required for QuickJS `SharedArrayBuffer` execution.

### 3.2 Deployment Pre-Dumps and Storage Retention
- Every automated run of `deploy-aeza-production.yml` takes an immutable pre-deployment PostgreSQL dump via `pg_dump -Fc` stored on the host at `/home/deploy/jsnb-deploy-backups/aeza-production/`.
- Pruning routines retain pre-dumps for 14 days, preventing unbounded disk growth during active release cycles.

### 3.3 Routing, TLS, and Isolation Headers
- Cloudflare proxying to the Aeza origin operates with Full SSL mode over valid Cloudflare Origin CA certificates.
- Edge health verification in GitHub Actions asserted expected HTTP 200 responses and verified that security isolation headers remain intact after each deployment.

### 3.4 Authentication & Security Invariants
- **Passwordless OTP Authentication:** Authentication relies on email dispatch via the Resend API. Delivery succeeded across all test authentications during deployment verification.
- **Session Validation:** JWT tokens signed with `HS256` validated successfully.
- **Security Invariant:** `ALLOW_PLACEHOLDER_AUTH=false` is enforced in production configuration, preventing any mock user authentications in the live environment.

### 3.5 Cloud AI Service & OpenRouter Integration
- **Default Provider:** OpenRouter is the active production cloud provider (`LLM_PROVIDER=openrouter`).
- **Access Restrictions:** Access is restricted to allowlisted developer accounts via `LLM_ALLOWED_EMAILS`. Non-allowlisted users receive HTTP 403 `llm_access_denied`.
- **Usage Controls (Step 8e):** Fail-closed reservation mechanisms and database-backed quota ledgers protect against unbounded model calls.
- **Key Handling & Preflight:**
  - *Development / Testing:* When `LLM_OPENROUTER_API_KEY` is missing or whitespace-only, `openrouter_client.py` raises `LlmProviderNotConfiguredError`, returning HTTP 503 (`service_unavailable` / `provider_not_configured`) without making upstream network calls.
  - *Production Startup:* Missing or empty `LLM_OPENROUTER_API_KEY` is caught at server startup by Pydantic settings validation (`app/core/config.py`), preventing the API service from starting without credentials.
  - *Invalid / Malformed Keys:* Non-empty invalid keys pass local preflight and are dispatched to OpenRouter, where they receive upstream HTTP 4xx error responses.

---

## 4. Operational Boundaries & Unverified Telemetry Gaps

To maintain strict engineering rigor, the following areas are explicitly documented as unverified by continuous telemetry:
1. **Continuous Host Telemetry:** Persistent host CPU and RAM utilization time-series data (e.g., via Prometheus/Grafana or CloudWatch-style agents) are not currently exported from the Aeza VPS. Steady-state numbers are derived from point-in-time checks rather than 24/7 time-series aggregations.
2. **Edge Access Logging:** Cloudflare Analytics aggregate request and error rate logs (5xx rates over time) are maintained within Cloudflare's external console and are not ingested into the monorepo.
3. **Continuous Resend Delivery Metrics:** Ongoing delivery metrics and bounce/timeout rates reside in the external Resend dashboard and are not polled continuously by the application.
4. **Third-Party Uptime Probing:** External synthetic monitoring probes (e.g., Pingdom or Better Uptime) are not currently registered as automated repository status checks.

---

## 5. Status of Remaining Operational Gates

The remaining operational items in the migration plan continue to be tracked as pending `[ ]`:

1. **Phase G Observation Gate:**
   - *Status:* Pending continuous telemetry attachment or explicit operator sign-off.
   - *Tracking:* [`aeza-migration-implementation-plan.md`](./aeza-migration-implementation-plan.md) §Phase G, items 190 and 246.
2. **Aeza Host `.env.prod` AWS Credential Sanitation & IAM Revocation:**
   - *Status:* Pending manual operator verification on the Aeza VPS.
   - *Tracking:* [`aeza-migration-implementation-plan.md`](./aeza-migration-implementation-plan.md) §Phase G, item 206.
3. **Pinned Guard Model Verification:**
   - *Status:* Pending repeated validation; roadmap context in [`larchanka-training/js-notebook#185`](https://github.com/larchanka-training/js-notebook/issues/185).
   - *Tracking:* [`aeza-migration-implementation-plan.md`](./aeza-migration-implementation-plan.md) §5, item 241; [`project.md`](./project.md) line 35.
4. **Automated Off-Host Backup Restore Verification:**
   - *Status:* Backup tooling merged in [`larchanka-training/dmc-1-t2-notebook-mono#237`](https://github.com/larchanka-training/dmc-1-t2-notebook-mono/pull/237); host cron activation and off-host restore drill pending under issue [`larchanka-training/js-notebook#158`](https://github.com/larchanka-training/js-notebook/issues/158).
   - *Tracking:* [`aeza-migration-implementation-plan.md`](./aeza-migration-implementation-plan.md) §5, item 243; [`project.md`](./project.md) line 34.
