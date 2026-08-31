# GitHub Repository Settings

This document describes the recommended GitHub repository settings for the JS Notebook project. It can be used as a checklist for the monorepo and the submodule repositories.

## Project Repositories

| Repository | Purpose |
| --- | --- |
| `dmc-1-t2-notebook-mono` | Monorepo, Docker Compose, CI workflows, shared documentation, submodule pointers |
| `dmc-1-t2-notebook-api` | Backend FastAPI service |
| `dmc-1-t2-notebook-ui` | Frontend React/Vite service |

Abbreviations:

- **FE** — frontend, the `ui` submodule/folder
- **BE** — backend, the `api` submodule/folder

## Goals of the Settings

- Prevent accidental direct changes to `main`.
- Route changes through pull requests.
- Require successful GitHub Actions checks before merge.
- Protect private submodules and secrets.
- Make the review process consistent across the whole team.
- Automate dependency updates via Dependabot.

## Branch Protection / Rulesets

It is recommended to use GitHub Rulesets for the `main` branch.

Path in the GitHub UI:

```text
Repository -> Settings -> Rules -> Rulesets -> New ruleset
```

Recommended settings:

| Setting | Recommendation | Why |
| --- | --- | --- |
| Ruleset name | `Protect main` | A clear name for the rule |
| Enforcement status | `Active` | The rule is actually applied |
| Target branches | `main` | Protects the main branch |
| Restrict deletions | Enabled | Prevents deletion of `main` |
| Require linear history | Optional | Enable if the team has agreed on squash/rebase |
| Require pull request | Enabled | All changes go through a PR |
| Required approvals | `1` | At least one review |
| Dismiss stale approvals | Recommended | An old approval is dismissed after new commits |
| Require conversation resolution | Enabled | Merge is blocked while discussions remain open |
| Require status checks | Enabled | Merge is blocked when CI is red |
| Block force pushes | Enabled | Protects the `main` history |

## Required Status Checks

For a monorepo it makes sense to require checks that correspond to the changed part of the project. At the same time, the current workflows use `paths` filters, so they cannot be blindly enabled as global required checks for every PR.

Current CI jobs:

| Workflow | When it runs | Make required now? | Comment |
| --- | --- | --- | --- |
| Docker Compose CI | PR (`api`/`ui`/`proxy`/compose) | Candidate, not global required | The integration monorepo PR gate; does not appear on docs-only PRs |
| GHCR Publish -> Build images | push `main` / tag `v*.*.*` | Not required | Publishes immutable `api/ui/migrations-sha-<short>` images to GHCR; not a PR gate |
| Deploy - Beget VPS | successful GHCR publish on `main`, production config push, or manual rollback | Not required | Current production deployment; remains unchanged until the approved Aeza cutover |
| Deploy - Aeza Staging | manual `workflow_dispatch` with an immutable `sha-*` tag | Not required | Isolated staging deployment through the `aeza-staging` Environment; never a PR gate |
| Autotests | PR paths, nightly schedule, or manual | Candidate, not global required | Containerized API and Playwright release regression; path-filtered on PRs |

The retired AWS ECR/ECS/CloudFront/Terraform and per-PR preview workflows are
archived under `archive/aws-workflows/` and are not active checks.

Per-module lint/tests live in the submodules' own CI (the `api`/`ui` repos), not in the monorepo.

Important: in the monorepo, workflows run with a `paths` filter:

- `Docker Compose CI` runs only on changes to runtime/Docker Compose paths (including bumps of the `api`/`ui` submodule pointers).
- `GHCR Publish` does not run on a PR; on `main` or a `v*.*.*` tag it publishes
  immutable images to GitHub Container Registry.

If a check is made required in the ruleset but the corresponding workflow did not run because of the `paths` filter, GitHub may leave the required check in `Pending` and block the merge. Therefore the current safe policy for this learning project is:

1. Keep the `paths` filters so as not to run unnecessary CI jobs on docs-only PRs.
2. Do not enable path-filtered checks as global required checks for all PRs.
3. Use the table above as a list of candidate checks for manual verification by the reviewer.
4. Enable global required checks only after an always-running gate workflow appears, or after deciding to run CI on every PR.

A docs-only PR without API/UI/Docker checks is expected behavior, not a bug.

If GitHub does not allow conveniently setting up conditional required checks for different paths, there are three possible approaches:

1. Require only the checks that actually appear for the PR.
2. Remove the `paths` filters and run both CI workflows on every PR.
3. Add a separate always-running CI Gate workflow that itself decides which checks are relevant for the changed paths.

For the current stage, the safe option was chosen: keep the `paths` filters and document the limitations. The CI Gate workflow can be added as a separate task if the team wants strict required checks without unnecessary runs.

## Current Ruleset Recommendation For `main`

The recommended ruleset configuration for the current stage of the project:

| Rule | Value | Comment |
| --- | --- | --- |
| Ruleset name | `Protect main` | The main rule for `main` |
| Enforcement status | `Active` | Enable after agreeing with the team |
| Target branches | `main` | Protects the default branch |
| Restrict deletions | Enabled | Prevents deletion of `main` |
| Block force pushes | Enabled | Prevents rewriting the `main` history |
| Require pull request before merging | Enabled | All changes go through a PR |
| Required approvals | `1` | A minimal review gate |
| Dismiss stale approvals | Recommended | Dismiss the approval after new commits |
| Require conversation resolution | Enabled | Do not merge with open discussions |
| Require status checks to pass | Use carefully | Do not enable path-filtered checks globally without a CI Gate |
| Require deployments to succeed | Disabled now | Preview/dev deploy will be a separate task for the next DevOps |

The minimal safe configuration for now: PR review + conversation resolution + blocking force push/deletion. Enable required checks only if the team understands the behavior of `paths` filters.

## Pull Request Rules

Recommended rules for all repositories:

| Setting | Recommendation |
| --- | --- |
| Merge via PR | Required |
| Minimum approvals | `1` |
| Self-approval | Do not use |
| Conversation resolution | Required |
| Delete branch after merge | Enabled |
| Auto-merge | Optional, better later |

## Merge Strategy

Path:

```text
Repository -> Settings -> General -> Pull Requests
```

Recommendation for this learning project:

| Strategy | Recommendation | Why |
| --- | --- | --- |
| Squash merge | Enabled, default | Clean main history, one commit per PR |
| Merge commit | Optional | Merge commits are visible, but the history is noisier |
| Rebase merge | Optional | Requires care with the history |

Recommended default: `Squash merge`.

## GitHub Actions Permissions

Path:

```text
Repository -> Settings -> Actions -> General
```

Recommended settings:

| Setting | Recommendation |
| --- | --- |
| Actions permissions | Allow all actions and reusable workflows, or allow selected trusted actions |
| Workflow permissions | Read repository contents permission |
| Allow GitHub Actions to create and approve pull requests | Disabled, unless there is a dedicated workflow for it |

If a workflow needs to push commits, tags, or packages, write permissions should be discussed separately and granted narrowly.

## Environments Protection

Active and planned GitHub Environments:

```text
production
aeza-staging
```

Path:

```text
Repository -> Settings -> Environments
```

Recommendations:

| Environment | Recommendation | Why |
| --- | --- | --- |
| `production` | Keep the existing Beget protection unchanged until cutover; require a reviewer for manual rollback/cutover actions | Prevents staging work from changing current production |
| `aeza-staging` | Create now; required reviewer recommended, deployment URL `https://staging.jsnb.org` | Isolates Aeza SSH material and makes every staging deployment explicit |

Do not store runtime `.env.prod` values in either GitHub Environment. The
server-local file remains the runtime secret boundary.

## Secrets and Variables

Path:

```text
Repository -> Settings -> Secrets and variables -> Actions
```

### Repository Secrets

| Secret | Where it is needed | Purpose |
| --- | --- | --- |
| `GH_PAT` | image builds and private submodule checkout | Read access to the monorepo and both submodule repositories |
| `BEGET_HOST` | `deploy-beget.yml` | Current production VPS address; retain until Aeza cutover is accepted |
| `BEGET_USER` | `deploy-beget.yml` | Current production deployment user |
| `BEGET_SSH_KEY` | `deploy-beget.yml` | Current production deployment key |

The staging SSH values below belong in the **`aeza-staging` Environment**, not
as repository-wide secrets:

| Environment secret | Purpose |
| --- | --- |
| `AEZA_STAGING_HOST` | Aeza staging IPv4/hostname |
| `AEZA_STAGING_USER` | unprivileged deployment user (`deploy`) |
| `AEZA_STAGING_SSH_KEY` | dedicated private SSH key |
| `AEZA_STAGING_SSH_PASSPHRASE` | private-key passphrase, when configured |
| `AEZA_STAGING_HOST_FINGERPRINT` | pinned SSH host-key SHA256 fingerprint |

Application runtime values such as database credentials, JWT/OTP secrets,
Resend, OpenRouter, and the developer allowlist live only in each server's
`.env.prod` with mode `600`. They must not be copied into workflow YAML or
GitHub repository secrets.

`GH_PAT` must have access to:

- `dmc-1-t2-notebook-mono`;
- `dmc-1-t2-notebook-api`;
- `dmc-1-t2-notebook-ui`.

Minimum required permissions:

- repository metadata read;
- repository contents read.

If GitHub requires approval for an organization token, the token must be approved by an organization administrator.

### Repository Variables

| Variable | Where it is needed | Example |
| --- | --- | --- |
| `VITE_API_BASE_URL` | UI image build | `/api/v1` |

The active VPS workflows do not require AWS deployment variables. Historical
AWS settings may remain only while an archived workflow or an external process
still references them; otherwise remove them after the Aeza production cutover.

Variables are suitable for non-secret values. Secrets are needed for tokens, passwords, and keys.

## Dependabot

Path:

```text
Repository -> Settings -> Code security and analysis -> Dependabot
```

It is recommended to enable:

- Dependabot alerts;
- Dependabot security updates;
- Dependabot version updates.

Recommended ecosystems:

| Repository | Ecosystem |
| --- | --- |
| monorepo | `github-actions` |
| api | `pip`, or `uv` if we later switch to uv |
| ui | `pnpm` |

For private submodules, Dependabot must also have access to the required repositories.

## Issue Templates

It is recommended to add `.github/ISSUE_TEMPLATE/`.

Minimal set:

| Template | For what |
| --- | --- |
| `bug_report.md` | Bugs |
| `feature_request.md` | New features |
| `devops_task.md` | CI/CD, Docker, GitHub settings, deployment |

Example of required fields:

- Context;
- What should be done;
- Acceptance criteria;
- Related links;
- How to verify.

## Pull Request Template

Recommended file:

```text
.github/pull_request_template.md
```

Minimal template:

```markdown
## What changed

-

## Why

-

## Verification

- [ ] Local checks have been run
- [ ] GitHub Actions passed
- [ ] Docker build verified if the runtime changed

## Related issue

Closes #
```

## CODEOWNERS

Recommended file:

```text
.github/CODEOWNERS
```

Example:

```text
.github/workflows/ @team-or-user
docs/ @team-or-user
api/ @backend-team-or-user
ui/ @frontend-team-or-user
proxy/ @devops-team-or-user
docker-compose.yaml @devops-team-or-user
```

CODEOWNERS should be enabled after the team agrees on who is responsible for each area of the project.

## Security

Recommended settings:

| Setting | Recommendation |
| --- | --- |
| Secret scanning | Enabled, if available |
| Push protection | Enabled, if available |
| Dependabot alerts | Enabled |
| Private vulnerability reporting | Optional |
| Branch force-push | Disabled for `main` |
| Branch deletion | Disabled for `main` |

## Recommended Setup Order

1. Set up `GH_PAT` and make sure CI can check out private submodules.
2. Enable GitHub Actions.
3. Configure the Ruleset for `main`.
4. Enable required PR review.
5. Define the policy for required status checks, taking into account the `paths` filters.
6. Enable delete branch after merge.
7. Configure Dependabot.
8. Add a PR template.
9. Add issue templates.
10. Add CODEOWNERS after agreeing on areas of responsibility.
11. For the `production` environment, enable required reviewers before a real deploy.

## Verification After Setup

Create a test PR and check that:

- a direct push to `main` is forbidden;
- a PR cannot be merged before the required checks complete;
- a PR cannot be merged with failed checks;
- a PR cannot be merged without the required approval;
- the feature branch is deleted after merge;
- GitHub Actions successfully pulls in the `api` and `ui` submodules.

## Active DevOps Handoff: Aeza Migration

The active DevOps scope is the time-bounded Beget-to-Aeza migration documented
in [`aeza-migration-implementation-plan.md`](aeza-migration-implementation-plan.md).
Beget production is paid through 2026-09-18, so the initial production cutover
must occur no later than 2026-09-16.

What is already available:

| Done | Where |
| --- | --- |
| Per-module CI (lint/tests) | submodules' CI: `api/.github/workflows/`, `ui/.github/workflows/` |
| Docker Compose smoke test | `.github/workflows/docker-compose-ci.yml` |
| GHCR image publication | `.github/workflows/ghcr-publish.yml`, `build-images.yml` |
| Current Beget production deployment | `.github/workflows/deploy-beget.yml` |
| Manual Aeza staging deployment | `.github/workflows/deploy-aeza-staging.yml` |
| Shared VPS Compose definition | `docker-compose.prod.yaml` |
| Cloudflare origin proxy/TLS configuration | `proxy/nginx.prod.conf`, server-local certificates |
| Deployment and migration docs | `docs/ci-cd.md`, `docs/aeza-migration-implementation-plan.md` |
| GitHub Environments | `production`; add `aeza-staging` |

The next gates are staging deploy/rollback proof, pinned OpenRouter models,
provider-neutral Cloud UI, off-host backups plus a restore rehearsal, a 72-hour
soak, production database rehearsal, and the controlled Cloudflare cutover.

The retired AWS and preview-v2 designs remain historical references only. Do
not restore their workflows or secrets as part of the Aeza migration.

## Useful Links

- Rulesets: https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-rulesets/about-rulesets
- Protected branches: https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-protected-branches/about-protected-branches
- Required status checks: https://docs.github.com/en/pull-requests/collaborating-with-pull-requests/collaborating-on-repositories-with-code-quality-features/troubleshooting-required-status-checks
- GitHub Actions permissions: https://docs.github.com/en/actions/security-guides/automatic-token-authentication
- Repository secrets: https://docs.github.com/en/actions/security-guides/using-secrets-in-github-actions
- Dependabot: https://docs.github.com/en/code-security/dependabot
- CODEOWNERS: https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/customizing-your-repository/about-code-owners
