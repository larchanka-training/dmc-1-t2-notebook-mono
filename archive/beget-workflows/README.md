# Beget Workflow Archive

**Archived:** 2026-09-22
**Reason:** Production cut over from Beget VPS to Aeza VPS on 2026-09-13. Automated deployment (`deploy-aeza-production.yml`), hardened health gates, immutable rollback, and roll-forward were verified in GitHub Actions on 2026-09-14/15. The Beget application stack is stopped and the workflow is retired.
**Historical reference tag:** `aeza-cutover-2026-09-13`

These files are kept for historical reference. They are NOT in `.github/workflows/` and therefore do NOT run.

## Files

| File | What it did |
|---|---|
| `deploy-beget.yml` | Deployed production stack to Beget VPS over SSH (git reset, GHCR pull, Liquibase migrations container, compose up, health check). |

## Active Production Deployment

Production is orchestrated by `.github/workflows/deploy-aeza-production.yml` targeting the single Aeza VPS host (`jsnb.org`) using immutable `sha-<short>` GHCR container images.

See also:
- [`docs/aeza-migration-implementation-plan.md`](../../docs/aeza-migration-implementation-plan.md) — Migration plan and phase checklist
- [`docs/ci-cd.md`](../../docs/ci-cd.md) — Production deployment documentation
- [`docs/github-repository-settings.md`](../../docs/github-repository-settings.md) — GitHub environment and secret configuration
