# GitHub Actions PR Checks

This document explains how the team uses GitHub Actions in pull requests, how to read check statuses, and when a PR can be merged.

## What PR Checks Are

When a pull request to `main` is created, GitHub runs the workflows from `.github/workflows/`.

Our monorepo has two main CI workflows:

| Workflow | File | When it runs | What it checks |
| --- | --- | --- | --- |
| API CI | `.github/workflows/api-ci.yml` | PR/push to `main` if `api/**` or the workflow itself changed | backend lint, backend tests, Docker build API |
| UI CI | `.github/workflows/ui-ci.yml` | PR/push to `main` if `ui/**` or the workflow itself changed | frontend lint, build, Docker build UI |

If a PR changes only the backend, only `API CI` may run. If a PR changes only documentation outside `api/**` and `ui/**`, these workflows may not run because of the `paths` filter.

## How CI Works in Our Monorepo

In CI, the GitHub runner first clones the monorepo and then pulls in the private submodules:

- `api`
- `ui`

A repository secret is used for this:

```yaml
token: ${{ secrets.GH_PAT }}
submodules: recursive
```

If `GH_PAT` does not have access to the private submodules, CI fails on checkout before lint/test/build runs.

A typical error:

```text
fatal: unable to access '...dmc-1-t2-notebook-api.git/': The requested URL returned error: 403
remote: Write access to repository not granted.
```

If the `Checkout submodules` step is green, the token works and CI has reached the project's actual checks.

## Which Checks Must Pass

### API CI

| Job | What it does | What a failure means |
| --- | --- | --- |
| `Lint` | Installs Python dependencies and runs `ruff check .` | An error in style, imports, unused code, or the ruff configuration |
| `Test` | Installs dev dependencies and runs `pytest` | Backend behavior or the test configuration is broken |
| `Docker Build` | Builds a Docker image from `api/Dockerfile` | The backend does not build in a production-like Docker runtime |

### UI CI

| Job | What it does | What a failure means |
| --- | --- | --- |
| `Lint` | Installs pnpm dependencies and runs ESLint | A frontend lint error |
| `Build` | Runs the production build of the UI | A TypeScript/Vite/build error |
| `Docker Build` | Builds a Docker image from `ui/Dockerfile` | The UI does not build in the Docker runtime |

## When a PR Can Be Merged

A PR can be merged when all of the following conditions are met:

1. There are no merge conflicts.
2. All relevant checks are green.
3. The review/approval matches the team's rules.
4. The PR has no unresolved discussion threads.
5. If the PR updates a submodule pointer, the commit in the submodule has already been pushed and is available in the remote repo.

Important: green CI does not replace review. CI checks automated scenarios, but it does not verify architectural decisions, requirements completeness, or the correctness of business logic.

## How to Read a PR Status

At the bottom of a PR, GitHub shows the checks.

| Status | Meaning | What to do |
| --- | --- | --- |
| Green / success | The check passed | You can move on to review/merge |
| Red / failure | The check failed | Open the failed job and look at the first meaningful error |
| Yellow / pending | The check is still running | Wait for it to finish |
| Skipped | The workflow/job did not run because of its conditions | Check whether this is expected for the current PR |

## How to View Logs Through the GitHub UI

1. Open the PR.
2. Find the checks block at the bottom.
3. Click `Details` for the workflow you need.
4. Open the failed job.
5. Find the first step with an error.

Usually, you should look not at the last stack trace but at the first step where the real cause appeared.

## How to View Logs Through the GitHub CLI

List the latest runs:

```bash
gh run list --repo larchanka-training/dmc-1-t2-notebook-mono --limit 10
```

View the details of a run:

```bash
gh run view <RUN_ID> --repo larchanka-training/dmc-1-t2-notebook-mono
```

View the failed logs:

```bash
gh run view <RUN_ID> --repo larchanka-training/dmc-1-t2-notebook-mono --log-failed
```

Check the checks of a specific PR:

```bash
gh pr checks <PR_NUMBER> --repo larchanka-training/dmc-1-t2-notebook-mono
```

## Common Problems

### Checkout submodules Fails

The cause is usually in `GH_PAT`.

Check that:

- the `GH_PAT` secret exists in the monorepo settings;
- the token is approved in the organization;
- the token has access to `dmc-1-t2-notebook-mono`, `dmc-1-t2-notebook-api`, `dmc-1-t2-notebook-ui`;
- the token has at least read access to the contents of private repositories.

### Lint Fails

Run the corresponding command locally:

```bash
cd api
ruff check .
```

or:

```bash
cd ui
pnpm run lint
```

### Tests Fail

Run locally:

```bash
cd api
pytest
```

or, for the UI once tests are set up:

```bash
cd ui
pnpm test
```

### Docker Build Fails

Run locally from the monorepo root:

```bash
docker build -t js-notebook-api:local ./api
docker build --target production -t js-notebook-ui:local ./ui
```

If it passes locally but fails in GitHub Actions, check the differences in env, secrets, network, and the base image.

## How to Use This in the Workflow

The recommended order for a PR:

1. Create a branch.
2. Make the changes.
3. Check the minimal commands locally.
4. Push the branch.
5. Create a PR.
6. Wait for GitHub Actions.
7. If the checks are red, fix them and push a new commit.
8. If the checks are green, request a review.
9. After approval and with no conflicts, perform the merge.
10. After the merge, delete the feature branch.

## Useful Links

- GitHub Actions workflow syntax: https://docs.github.com/actions/reference/workflows-and-actions/workflow-syntax
- Events that trigger workflows: https://docs.github.com/actions/learn-github-actions/events-that-trigger-workflows
- Troubleshooting required status checks: https://docs.github.com/en/pull-requests/collaborating-with-pull-requests/collaborating-on-repositories-with-code-quality-features/troubleshooting-required-status-checks
- Protected branches and required checks: https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-protected-branches/about-protected-branches
