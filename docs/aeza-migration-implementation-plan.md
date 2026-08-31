# Aeza staging and production migration implementation plan

> **Status:** approved and in progress
> **Decision date:** 2026-08-30
> **Tracker:** [`larchanka-training/js-notebook#187`](https://github.com/larchanka-training/js-notebook/issues/187)
> **Current production:** Beget VPS, paid through 2026-09-18
> **Target:** complete the production move to the Aeza VPS before the Beget
> service period ends
> **Operational deadline:** cut over no later than 2026-09-16, preserve
> 2026-09-17 and 2026-09-18 for observation and decommissioning

## 1. Decision and boundaries

The Aeza VPS is paid for one month and becomes the project's staging host now
and the intended single production host after the migration gates pass. Running
two application servers long-term is explicitly out of scope.

Until the cutover phase:

- `https://jsnb.org` and the existing automatic production deployment remain
  on Beget;
- `https://staging.jsnb.org` remains on Aeza;
- `.github/workflows/deploy-beget.yml`, Beget secrets, production DNS, and the
  Beget runtime configuration are not changed;
- Aeza deployments are manual and require an explicit immutable image tag;
- staging uses a separate Docker Compose project (`jsnotes-staging`) and GitHub
  Environment (`aeza-staging`).

## 2. Verified Aeza baseline

The following checks were completed on 2026-08-29/30:

- Ubuntu 24.04 is updated and booted into the updated kernel;
- SSH root/password login is disabled; the `deploy` user uses a dedicated key;
- UFW allows only SSH, HTTP, and HTTPS ingress;
- Docker Engine and Docker Compose are installed;
- the host has 2 GiB swap with `vm.swappiness=10`;
- the monorepo and submodules are checked out on the server;
- GHCR API, UI, and migrations images can be pulled;
- PostgreSQL starts healthy and all production-context Liquibase migrations run;
- the API, UI, PostgreSQL, and proxy containers run under `jsnotes-staging`;
- Cloudflare-proxied `staging.jsnb.org` and the origin certificate work;
- the public health endpoint returns `status=ok` and `environment=staging`;
- the Aeza egress location can reach OpenRouter;
- a real authenticated `/api/v1/llm/generate` request completed through
  OpenRouter, and the metadata-only log safety checks passed.

## 3. Delivery phases

### Phase A - separate Aeza staging deployment

Target: 2026-08-30 through 2026-09-02.

- [ ] Merge `.github/workflows/deploy-aeza-staging.yml`.
- [ ] Create the protected GitHub Environment `aeza-staging`.
- [ ] Add only the environment secrets documented in `docs/ci-cd.md`.
- [ ] Run the workflow manually with a known `sha-*` image tag.
- [ ] Confirm repository sync, image verification, migrations, origin health,
      and public Cloudflare health in the workflow log.
- [ ] Run a second deployment with the same tag to prove idempotency.
- [ ] Run a manual rollback to one previously verified immutable image tag.

Exit gate: staging deploy and rollback both succeed without changing Beget.

### Phase B - stabilize the OpenRouter path

Target: 2026-09-02 through 2026-09-06.

- [ ] Keep the server-side developer email allowlist enabled.
- [ ] Replace `openrouter/free` for the guard with a pinned model that reliably
      returns strict JSON; verify it with repeated isolated guard calls first.
- [ ] Decide whether the generator remains on `openrouter/free` for private
      staging or is also pinned.
- [ ] Keep free-tier use limited to developer validation.
- [ ] Record the observed transient failure where the dynamic free router made
      the guard return invalid JSON and the next request succeeded.
- [ ] After OpenRouter credits are purchased, recheck `/api/v1/key`, model
      availability, provider limits, and the project's global/per-user caps
      before expanding access.
- [ ] Do not equate paid OpenRouter credits with unlimited product access:
      application-side quotas and usage accounting remain required.

Exit gate: repeated guard and generation checks succeed with pinned production
model IDs and bounded quotas.

### Phase C - finish the Cloud LLM user interface

Target: 2026-09-02 through 2026-09-07. Track this work in the implementation
roadmap; it is deliberately not bundled into the infrastructure workflow PR.

- [ ] Wire the markdown-cell Cloud button to
      `cloudGenerateAndInsertCodeAction`; it is currently always disabled
      because `NotebookView` does not pass `onCloudGenerate`.
- [ ] Keep the explicit user-controlled LLM master switch.
- [ ] Replace `Cloud (AWS Bedrock)` and other provider-specific UI text with
      provider-neutral `Cloud AI` wording.
- [ ] Make the Playground sign-in badge reflect actual authentication state or
      remove it from the already protected route.
- [ ] Verify the Playground can send to Cloud when no in-browser model is loaded.
- [ ] Preserve the rule that generated code is inserted but never auto-executed.
- [ ] Add browser coverage for Cloud success, provider failure, retry, allowlist
      denial, and disabled-feature states.

Exit gate: the notebook and Playground expose the same working provider-neutral
Cloud flow for allowlisted authenticated users.

### Phase D - backups and restore rehearsal

Target: 2026-09-03 through 2026-09-09.

- [ ] Create a daily compressed `pg_dump` job on Aeza.
- [ ] Retain multiple dated copies with a documented rotation policy.
- [ ] Copy backups off the Aeza VPS; provider snapshots alone are insufficient.
- [ ] Ensure backup files and credentials are readable only by the deployment
      operator.
- [ ] Add success/failure logging and a disk-space guard.
- [ ] Restore one backup into a disposable database and verify row counts,
      authentication, notebooks, and Liquibase history.
- [ ] Document backup, restore, and emergency rollback commands without secrets.

Exit gate: a fresh off-host backup has been restored and functionally checked.

### Phase E - staging soak and release rehearsal

Target: 2026-09-07 through 2026-09-12.

- [ ] Observe staging for at least 72 hours after the deployment workflow and
      pinned guard are active.
- [ ] Exercise OTP login, refresh/logout, notebook CRUD/autosync, browser code
      execution, Cloud LLM generation, and error handling.
- [ ] Review container health, restarts, memory, swap, disk usage, API errors,
      proxy 5xx responses, and OpenRouter quota usage.
- [ ] Run the containerized regression suite required by `AGENTS.md`.
- [ ] Rehearse the Beget-to-Aeza database copy using a non-production restore.
- [ ] Record exact timings for dump, transfer, restore, migration, and smoke.

Exit gate: no unresolved severity-high defect and the migration fits inside the
chosen maintenance window.

### Phase F - production cutover

Target: 2026-09-15 or 2026-09-16. Do not schedule the initial cutover on
2026-09-18, because that leaves no recovery margin before Beget expires.

1. Announce and enter a maintenance window that prevents writes on Beget.
2. Take and verify the final Beget database dump.
3. Transfer the dump over an authenticated encrypted channel.
4. Restore it into the Aeza production database and run Liquibase migrations.
5. Change the Aeza runtime from staging to the reviewed production environment
   without exposing secrets in Git or workflow logs.
6. Start the Aeza stack with the production Compose project name.
7. Smoke-test the Aeza origin before changing public routing.
8. Point the Cloudflare `jsnb.org` origin to Aeza while keeping the record
   proxied and the configured SSL mode unchanged.
9. Verify public health, TLS, security headers, OTP login, notebook sync, and an
   allowlisted Cloud LLM request.
10. Reopen writes only after the acceptance checks pass.

Rollback boundary: rollback to Beget is straightforward only while writes are
still blocked. After writes reopen on Aeza, switching back to the stale Beget
database would lose data; any later rollback must first reconcile or restore the
new Aeza data.

### Phase G - observation and Beget retirement

Target: 2026-09-16 through 2026-09-18.

- [ ] Keep Beget available but unable to accept application writes during the
      observation window.
- [ ] Monitor Aeza health, restarts, resources, proxy errors, authentication,
      notebook writes, backups, and LLM failures.
- [ ] Preserve the final Beget dump off both servers.
- [ ] Convert the production deployment workflow and GitHub Environment to Aeza
      only after the cutover is accepted.
- [ ] Remove/revoke obsolete Beget deployment secrets and credentials.
- [ ] Remove obsolete AWS runtime credentials after confirming OpenRouter is the
      selected production provider and no remaining feature uses them.
- [ ] Cancel Beget by the end of its paid period.
- [ ] Update `AGENTS.md`, `docs/ci-cd.md`, architecture documentation, and the
      Project Dev roadmap to describe Aeza as the single production host.

Exit gate: Aeza is the single documented production host, backups are current,
and no active workflow or secret targets Beget.

## 4. GitHub staging environment

Create `aeza-staging` under Repository Settings -> Environments. The first
workflow version is manual-only, so required reviewers are optional but
recommended. Store connection material as environment secrets, not repository
variables and not in `.env.prod` committed to Git.

The staging deployment must never read `BEGET_*` secrets. Production and
staging concurrency groups must remain separate.

## 5. Go/no-go checklist for cancelling Beget

Do not cancel Beget until every item below is true:

- [ ] Aeza deployment and immutable rollback are proven through GitHub Actions.
- [ ] A pinned guard model has passed repeated checks.
- [ ] Cloud UI no longer advertises AWS Bedrock and its intended controls work.
- [ ] Automated off-host backups run and a restore was tested.
- [ ] Staging completed a 72-hour observation window.
- [ ] The production migration rehearsal completed within the maintenance limit.
- [ ] The final production cutover and acceptance tests passed.
- [ ] Post-cutover monitoring found no unresolved data or availability issue.
- [ ] The final Beget backup is stored off-host.
- [ ] GitHub workflows, secrets, and documentation no longer depend on Beget.
