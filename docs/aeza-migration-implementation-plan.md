# Aeza staging and production migration implementation plan

> **Status:** production cutover accepted; post-cutover automation and retirement in progress
> **Decision date:** 2026-08-30
> **Tracker:** [`larchanka-training/js-notebook#187`](https://github.com/larchanka-training/js-notebook/issues/187)
> **Current production:** Aeza VPS since 2026-09-13; Beget application stopped
> **Target:** complete deployment/backup automation and retire Beget before its
> service period ends
> **Operational deadline:** cut over no later than 2026-09-16, preserve
> 2026-09-17 and 2026-09-18 for observation and decommissioning

## 1. Decision and boundaries

The Aeza VPS is paid for one month and becomes the project's staging host now
and the intended single production host after the migration gates pass. Running
two application servers long-term is explicitly out of scope.

Historical pre-cutover boundaries were:

- `https://jsnb.org` and the existing automatic production deployment remain
  on Beget;
- `https://staging.jsnb.org` remains on Aeza;
- `.github/workflows/deploy-beget.yml`, Beget secrets, production DNS, and the
  Beget runtime configuration are not changed;
- Aeza deployments are manual and require an explicit immutable image tag;
- staging uses a separate Docker Compose project (`jsnotes-staging`) and GitHub
  Environment (`aeza-staging`).

The cutover was completed and functionally accepted on 2026-09-13. The Aeza
production checkout is `/home/deploy/jsnb-production`, the Compose project is
`jsnotes-production`, and Cloudflare routes `jsnb.org` to that origin. The final
Beget dump was checksum-verified, restored on Aeza, and retained off both
servers. OTP sign-in, cross-browser notebook sync, browser execution, an
allowlisted Cloud AI request, and the non-allowlisted 403 path passed. The
former staging stack is stopped and `staging.jsnb.org` is authoritative
NXDOMAIN.

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

- [x] Merge `.github/workflows/deploy-aeza-staging.yml`.
- [x] Create the protected GitHub Environment `aeza-staging`.
- [x] Add only the environment secrets documented in `docs/ci-cd.md`.
- [x] Run the workflow manually with a known `sha-*` image tag.
- [x] Confirm repository sync, image verification, migrations, origin health,
      and public Cloudflare health in the workflow log.
- [x] Run a second deployment with the same tag to prove idempotency.
- [ ] Run a manual rollback to one previously verified immutable image tag that
      is compatible with the current forward-migrated database schema.
      (Not executed before staging retirement; deferred to the production
      workflow verification gate.)

Exit gate: staging deploy succeeded; rollback was not executed before staging
retirement and is deferred to production workflow verification. The image
rollback does not reverse Liquibase changesets; an incompatible schema
requires the tested backup/restore path instead of an image-only rollback.
Staging stack and DNS were retired during cutover on 2026-09-13.

### Phase B - stabilize the OpenRouter path

Target: 2026-09-02 through 2026-09-06.

- [x] Keep the server-side developer email allowlist enabled.
- [ ] Replace `openrouter/free` for the guard with a pinned model that reliably
      returns strict JSON; verify it with repeated isolated guard calls first.
- [ ] Decide whether the generator remains on `openrouter/free` for private
      staging or is also pinned.
- [x] Keep free-tier use limited to developer validation.
- [x] Record the observed transient failure where the dynamic free router made
      the guard return invalid JSON and the next request succeeded.
- [ ] After OpenRouter credits are purchased, recheck `/api/v1/key`, model
      availability, provider limits, and the project's global/per-user caps
      before expanding access.
- [x] Do not equate paid OpenRouter credits with unlimited product access:
      application-side quotas and usage accounting remain required.

Exit gate: repeated guard and generation checks succeed with pinned production
model IDs and bounded quotas.

### Phase C - finish the Cloud LLM user interface

Target: 2026-09-02 through 2026-09-07. Track this work in the implementation
roadmap; it is deliberately not bundled into the infrastructure workflow PR.

- [x] Wire the markdown-cell Cloud button to
      `cloudGenerateAndInsertCodeAction` (historically disabled because
      `NotebookView` did not pass `onCloudGenerate`; now wired and active).
- [x] Keep the explicit user-controlled LLM master switch.
- [x] Replace `Cloud (AWS Bedrock)` and other provider-specific UI text with
      provider-neutral `Cloud AI` wording.
- [x] Make the Playground sign-in badge reflect actual authentication state or
      remove it from the already protected route.
- [x] Verify the Playground can send to Cloud when no in-browser model is loaded.
- [x] Preserve the rule that generated code is inserted but never auto-executed.
- [ ] Add full browser coverage for Cloud success, provider failure, retry, allowlist
      denial, and disabled-feature states. (Unit/component tests and manual
      smoke verified Cloud success, allowlist 403, and master switch; automated
      browser scenarios for provider failure and retry remain pending.)

Exit gate: the notebook and Playground expose the same working provider-neutral
Cloud flow for allowlisted authenticated users.

### Phase D - backups and restore rehearsal

Target: 2026-09-03 through 2026-09-09. Tooling implemented in PR #237; operational activation and off-host restore verification pending.

- [x] Create a daily compressed `pg_dump` script on Aeza (`scripts/backup-aeza.sh`).
- [x] Retain multiple dated copies with a documented rotation policy (14 daily / 4 weekly).
- [x] Ensure backup files and credentials are readable only by the deployment
      operator (modes 0700 / 0600).
- [x] Add success/failure logging, pre-flight disk guard, and plaintext-excluded encrypted export bundle.
- [x] Implement disposable database restore verification with deterministic row-count equivalence checks (`scripts/restore-disposable-db.sh`).
- [x] Document backup, off-host replication, disposable restore, and DR commands (`docs/backup-restore.md`).
- [ ] Install and verify automated daily cron job on Aeza host (`0 3 * * *`).
- [ ] Configure and verify scheduled off-host replication.
- [ ] Decrypt and verify a fresh off-host backup in disposable database with post-cutover production data.

Exit gate: a fresh off-host backup has been decrypted, restored, and functionally checked (pre-cutover historical rehearsal completed 2026-09-12; post-cutover automated run pending operational execution).

### Phase E - staging soak and release rehearsal

Target: 2026-09-07 through 2026-09-12.

- [ ] Observe staging for at least 72 hours after the deployment workflow and
      pinned guard are active. (Waived on staging due to accelerated cutover;
      staging was retired with an unpinned guard. Replaced by post-cutover
      production observation in Phase G.)
- [x] Exercise OTP login, refresh/logout, notebook CRUD/autosync, browser code
      execution, Cloud LLM generation, and error handling.
- [x] Review container health, restarts, memory, swap, disk usage, API errors,
      proxy 5xx responses, and OpenRouter quota usage.
- [x] Run the containerized regression suite required by `AGENTS.md`.
- [x] Rehearse the Beget-to-Aeza database copy using a non-production restore.
- [x] Record exact timings for dump, transfer, restore, migration, and smoke.

Exit gate: no unresolved severity-high defect and the migration fits inside the
chosen maintenance window.

### Phase F - production cutover

Completed 2026-09-13. Functional smoke passed 2026-09-14 00:19 (+04:00).

- [x] Announce and enter a maintenance window that prevents writes on Beget.
- [x] Take and verify the final Beget database dump.
- [x] Transfer the dump over an authenticated encrypted channel.
- [x] Restore it into the Aeza production database and run Liquibase migrations.
- [x] Change the Aeza runtime from staging to the reviewed production environment
      without exposing secrets in Git or workflow logs.
- [x] Start the Aeza stack with the production Compose project name (`jsnotes-production`).
- [x] Smoke-test the Aeza origin before changing public routing.
- [x] Point the Cloudflare `jsnb.org` origin to Aeza while keeping the record
      proxied and the configured SSL mode unchanged.
- [x] Verify public health, TLS, security headers, OTP login, notebook sync, and an
      allowlisted Cloud LLM request.
- [x] Reopen writes only after the acceptance checks pass.

Rollback boundary: rollback to Beget is straightforward only while writes are
still blocked. After writes reopen on Aeza, switching back to the stale Beget
database would lose data; any later rollback must first reconcile or restore the
new Aeza data.

### Phase G - observation and Beget retirement

Target: 2026-09-16 through 2026-09-18.

- [x] Keep Beget available but unable to accept application writes during the
      observation window.
- [ ] Monitor Aeza health, restarts, resources, proxy errors, authentication,
      notebook writes, backups, and LLM failures.
- [x] Preserve the final Beget dump off both servers.
- [x] Convert the production deployment workflow and GitHub Environment to Aeza
      only after the cutover is accepted. Implementation merged in PR #233;
      environment secrets and first automated deploy `sha-7e81b92` verified on
      2026-09-14. Hardened health gates (`sha-731ca16` in run 34936010541),
      immutable rollback (`sha-7e81b92` in run 34936085722), and roll-forward
      (`sha-731ca16` in run 34936157711) verified on 2026-09-15.
- [x] Retire legacy Beget deployment workflow (`.github/workflows/deploy-beget.yml` moved to `archive/beget-workflows/deploy-beget.yml`).
- [x] Remove obsolete Beget deployment repository secrets (`BEGET_HOST`, `BEGET_USER`, `BEGET_SSH_KEY` confirmed removed from GitHub repository settings on 2026-09-22).
- [ ] Revoke deployment credentials on the Beget host / verify server-side SSH access removal.
- [ ] Remove obsolete AWS runtime credentials after confirming OpenRouter is the
      selected production provider and no remaining feature uses them.
- [ ] Cancel Beget by the end of its paid period.
- [x] Update `AGENTS.md`, `docs/ci-cd.md`, architecture documentation, and the
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

- [x] Aeza deployment, immutable rollback, and roll-forward are proven through GitHub Actions (deploy passed in runs 34825043090 and 34936010541; rollback to `sha-7e81b92` verified in run 34936085722; roll-forward to `sha-731ca16` verified in run 34936157711).
- [ ] A pinned guard model has passed repeated checks.
- [x] Cloud UI no longer advertises AWS Bedrock and its intended controls work.
- [ ] Automated off-host backups run and a restore was tested (tooling implemented in PR #237; host cron and off-host restore verification pending).
- [x] The production migration rehearsal completed within the maintenance limit.
- [x] The final production cutover and acceptance tests passed.
- [ ] Post-cutover production monitoring found no unresolved data or availability issue (Phase G).
- [x] The final Beget backup is stored off-host.
- [ ] GitHub workflows, secrets, and documentation no longer depend on Beget (workflow archived to `archive/beget-workflows/`; repository secrets removal and server credential revocation pending verification).

### Historical waivers

- **72-hour staging observation window:** Waived for the retired staging stack
  due to accelerated cutover with an unpinned guard. Governed instead by
  post-cutover production observation in Phase G.
