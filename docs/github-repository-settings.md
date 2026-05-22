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

| Workflow | Check | When it runs | Make required now? | Comment |
| --- | --- | --- | --- | --- |
| API CI | `API CI / Lint` | `api/**`, `.github/workflows/api-ci.yml` | Candidate, not global required | A good gate for backend PRs, but it does not appear on docs-only/frontend-only PRs |
| API CI | `API CI / Test` | `api/**`, `.github/workflows/api-ci.yml` | Candidate, not global required | Same limitation due to the `paths` filter |
| API CI | `API CI / Docker Build` | `api/**`, `.github/workflows/api-ci.yml` | Candidate, not global required | Same limitation due to the `paths` filter |
| UI CI | `UI CI / Lint` | `ui/**`, `.github/workflows/ui-ci.yml` | Candidate, not global required | A good gate for frontend PRs, but it does not appear on docs-only/backend-only PRs |
| UI CI | `UI CI / Build` | `ui/**`, `.github/workflows/ui-ci.yml` | Candidate, not global required | Same limitation due to the `paths` filter |
| UI CI | `UI CI / Docker Build` | `ui/**`, `.github/workflows/ui-ci.yml` | Candidate, not global required | Same limitation due to the `paths` filter |
| Docker Compose CI | `Docker Compose CI / Docker Compose Smoke Test` | `api/**`, `ui/**`, `proxy/**`, `docker-compose.yaml`, workflow file | Candidate, not global required | Does not appear on docs-only PRs |
| Docker Publish | `Docker Publish / Publish api image` | `api/**`, `ui/**`, workflow file, push/tag/manual | Not required | On a PR it runs a build without push; on `main` it publishes the image |
| Docker Publish | `Docker Publish / Publish ui image` | `api/**`, `ui/**`, workflow file, push/tag/manual | Not required | Same |
| Manual Deploy | `Manual Deploy / Validate deploy inputs` | `workflow_dispatch` only | Not required | A dry-run deploy workflow, not a PR gate |

Important: in the monorepo, workflows run with a `paths` filter:

- `API CI` runs on changes in `api/**` or `.github/workflows/api-ci.yml`;
- `UI CI` runs on changes in `ui/**` or `.github/workflows/ui-ci.yml`.
- `Docker Compose CI` runs only on changes to runtime/Docker Compose paths.
- `Docker Publish` does not push images on a PR, and publishes GHCR images on `main`.

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

GitHub Environments are already used for the manual deploy workflow:

```text
staging
production
```

Path:

```text
Repository -> Settings -> Environments
```

Recommendations:

| Environment | Recommendation | Why |
| --- | --- | --- |
| `staging` | No required reviewers at the current stage | Fast checks of the deployment wiring |
| `production` | Enable required reviewers | A production deploy should wait for manual approval |

The current `Manual Deploy` workflow is a dry-run: it validates inputs and `docker-compose.prod.yaml`, but does not connect to a server. Real secrets for AWS/SSH/deploy should be added only after the infrastructure for the next sprint is chosen.

## Secrets and Variables

Path:

```text
Repository -> Settings -> Secrets and variables -> Actions
```

### Repository Secrets

| Secret | Where it is needed | Purpose |
| --- | --- | --- |
| `GH_PAT` | monorepo | Checkout of private submodules in GitHub Actions |
| `DATABASE_URL` | API deploy later | Production database URL |
| `OAUTH_NAME_APPLICATION_ID` | API deploy later | OAuth app id |
| `OAUTH_NAME_SECRET_KEY` | API deploy later | OAuth secret |
| `TOKEN_TTL_SECONDS` | API deploy later | Access token TTL |
| `SESSION_TTL_SECONDS` | API deploy later | Session TTL |

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
| `VITE_API_BASE_URL` | UI CI / Docker build | `/api/v1` |

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

## Handoff for the Next DevOps: Preview + Dev Environments v2

The current DevOps scope closes the CI/CD foundation for the project. The next DevOps scope will extend the infrastructure into a "live" product:

- preview deployments for each branch / pull request;
- automatic deploy after a merge into the main branch;
- build caching optimization;
- working preview URLs for each PR;
- an updated CI/CD pipeline for the dev/production environments.

What is already done and can be used as a base:

| Done | Where |
| --- | --- |
| API/UI CI | `.github/workflows/api-ci.yml`, `.github/workflows/ui-ci.yml` |
| Docker Compose smoke test | `.github/workflows/docker-compose-ci.yml` |
| GHCR publish for API/UI images | `.github/workflows/docker-publish.yml` |
| Multi-arch images | `docker/build-push-action` in Docker Publish |
| Production compose from GHCR images | `docker-compose.prod.yaml` |
| Manual deploy dry-run | `.github/workflows/deploy.yml` |
| Deploy docs | `docs/deploy.md` |
| GitHub Environments | `staging`, `production` |

What is not part of the current scope and should be a separate task:

- AWS deploy;
- preview environments per branch;
- automatic deploy on merge to `main`;
- AWS IAM/OIDC roles;
- ECR vs GHCR registry decision;
- real dev/prod secrets;
- domain/TLS;
- rollback workflow;
- monitoring/logging.

Important: the current ruleset must not block future preview workflows. Once stable preview/dev deploy checks appear, the next DevOps should revisit the required checks and decide whether an always-running CI Gate workflow is needed.

## Useful Links

- Rulesets: https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-rulesets/about-rulesets
- Protected branches: https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-protected-branches/about-protected-branches
- Required status checks: https://docs.github.com/en/pull-requests/collaborating-with-pull-requests/collaborating-on-repositories-with-code-quality-features/troubleshooting-required-status-checks
- GitHub Actions permissions: https://docs.github.com/en/actions/security-guides/automatic-token-authentication
- Repository secrets: https://docs.github.com/en/actions/security-guides/using-secrets-in-github-actions
- Dependabot: https://docs.github.com/en/code-security/dependabot
- CODEOWNERS: https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/customizing-your-repository/about-code-owners
