# Sprint 3 Deliverables

This folder collects the Sprint 3 working documents and final artifacts for JS Notebook.

## Purpose

The goal of this folder is to keep all Sprint 3 deliverables in one place, with one file per role/workstream plus this overview document.

## Source Brief

The Sprint 3 brief includes the following workstreams and expected outputs.

### Tech Lead

- Task: conduct a technical audit of the project.
- Questions to answer:
  - What will break first?
  - What technical debt exists?
  - What are the release risks?
  - What should be done over the next 3 months?
- Deliverable: `TL-production-readiness.md`

### Engineer #1 — Usage Analytics

- Task: add product analytics.
- Track:
  - notebook creation
  - cell execution
  - AI requests
  - execution errors
- Deliverable: `E1-usage-analytics.md`
- Expected implementation artifact: dashboard + events

### Engineer #2 — Cost Optimization

- Task: estimate operating costs.
- Estimate:
  - AWS
  - Bedrock
  - storage
  - traffic
- Scenarios:
  - 100 users
  - 1,000 users
  - 10,000 users
- Deliverable: `E2-cost-analysis.md`

### Engineer #3 — Performance Investigation

- Task: conduct load and performance testing.
- Measure:
  - notebook open time
  - cell execution time
  - bundle size
  - API latency
- Include improvement proposals.
- Deliverable: `E3-performance-report.md`

### Engineer #4 — Security Audit

- Task: try to break the system.
- Check:
  - XSS
  - JWT
  - API authorization
  - execution sandbox
  - prompt injection
- Deliverable: `E4-security-review.md`

### Engineer #5 — Launch Presentation

- Task: prepare the final project presentation.
- Cover:
  - architecture
  - problems
  - solutions
  - mistakes
  - metrics
  - what worked best
  - what should be redesigned
- Deliverable: `E5-demo-day-outline.md`
- Expected output: 15–20 minute demo day presentation

### DevOps — Disaster Recovery Plan

- Task: prepare recovery scenarios.
- Describe:
  - database loss
  - API outage
  - AWS region outage
  - key leakage
  - Bedrock budget overrun
  - limit calculations / budget caps
- Deliverable: `DevOps-runbook.md`

### QA — Release Certification

- Task: complete a full regression cycle.
- Prepare:
  - list of critical bugs
  - list of known limitations
  - decision: Go / No Go
- Deliverable: `QA-release-report.md`

## File Map

- `TL-production-readiness.md` — technical audit and production-readiness assessment
- `E1-usage-analytics.md` — usage analytics plan, events, dashboard, implementation notes
- `E2-cost-analysis.md` — cost model and scenario-based estimates
- `E3-performance-report.md` — performance measurements and recommended improvements
- `E4-security-review.md` — security findings, attack attempts, and mitigations
- `DevOps-runbook.md` — disaster recovery and operational response runbook
- `QA-release-report.md` — release certification decision and test summary
- `E5-demo-day-outline.md` — presentation structure and speaking plan

## Notes

- These files start as templates and can be updated incrementally during the sprint.
- If implementation work changes architecture, infra, or public contracts, related project docs outside this folder must also be updated.
