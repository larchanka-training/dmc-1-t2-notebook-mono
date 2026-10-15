#!/usr/bin/env python3
"""Automated Incident Reporter for Nightly Autotest Failures and Recoveries."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from typing import Any, Callable

INCIDENT_TITLE = "🚨 Nightly Autotest Failure on main"
INCIDENT_LABEL = "nightly-incident"
METADATA_REGEX = re.compile(r"<!--\s*incident-metadata:\s*(\{.*?\})\s*-->")
RESOLUTION_REGEX = re.compile(r"<!--\s*resolution-metadata:\s*(\{.*?\})\s*-->")


class IncidentReporterError(Exception):
    """Raised when an operation in incident reporter fails."""


def run_gh_command(
    args: list[str],
    *,
    runner: Callable[..., subprocess.CompletedProcess[str]] | None = None,
) -> subprocess.CompletedProcess[str]:
    """Execute a GitHub CLI command."""
    exec_func = runner or subprocess.run
    return exec_func(
        ["gh", *args],
        capture_output=True,
        text=True,
        check=False,
    )


def ensure_label_exists(
    repo: str,
    label: str,
    *,
    color: str = "d73a4a",
    description: str = "Automated nightly autotest failure incident",
    runner: Callable[..., subprocess.CompletedProcess[str]] | None = None,
) -> None:
    """Ensure that the required label exists in the repository."""
    run_gh_command(
        [
            "label",
            "create",
            label,
            "--repo",
            repo,
            "--color",
            color,
            "--description",
            description,
            "--force",
        ],
        runner=runner,
    )


def find_incidents(
    repo: str,
    *,
    state: str = "open",
    limit: int = 10,
    runner: Callable[..., subprocess.CompletedProcess[str]] | None = None,
) -> list[dict[str, Any]]:
    """Query issues with the nightly-incident label filtered by state."""
    res = run_gh_command(
        [
            "issue",
            "list",
            "--repo",
            repo,
            "--state",
            state,
            "--label",
            INCIDENT_LABEL,
            "--json",
            "number,title,state,createdAt,updatedAt,body,comments",
            "--limit",
            str(limit),
        ],
        runner=runner,
    )
    if res.returncode != 0:
        raise IncidentReporterError(f"Failed to query issues: {res.stderr.strip()}")

    try:
        return json.loads(res.stdout or "[]")
    except json.JSONDecodeError as err:
        raise IncidentReporterError(f"Failed to parse issue list JSON: {err}")


def find_open_incident(
    repo: str,
    *,
    runner: Callable[..., subprocess.CompletedProcess[str]] | None = None,
) -> dict[str, Any] | None:
    """Find any open incident issue with the nightly-incident label."""
    issues = find_incidents(repo, state="open", limit=5, runner=runner)
    return issues[0] if issues else None


def extract_resolution_metadata(issue_data: dict[str, Any]) -> dict[str, Any] | None:
    """Extract resolution metadata from comments and body in reverse chronological order."""
    comments = issue_data.get("comments", [])
    if isinstance(comments, list):
        for comment in reversed(comments):
            if isinstance(comment, dict) and comment.get("body"):
                match = RESOLUTION_REGEX.search(comment["body"])
                if match:
                    try:
                        return json.loads(match.group(1))
                    except json.JSONDecodeError:
                        continue
    if issue_data.get("body"):
        match = RESOLUTION_REGEX.search(issue_data["body"])
        if match:
            try:
                return json.loads(match.group(1))
            except json.JSONDecodeError:
                pass
    return None


def find_latest_resolved_incident(
    repo: str,
    *,
    runner: Callable[..., subprocess.CompletedProcess[str]] | None = None,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    """Find the most recently closed incident and extract its resolution metadata if present."""
    closed_issues = find_incidents(repo, state="closed", limit=5, runner=runner)
    if not closed_issues:
        return None, None

    for issue in closed_issues:
        meta = extract_resolution_metadata(issue)
        if meta:
            return issue, meta
    return closed_issues[0], None


def get_latest_successful_scheduled_run(
    repo: str,
    workflow: str = "autotests.yml",
    branch: str = "main",
    *,
    runner: Callable[..., subprocess.CompletedProcess[str]] | None = None,
) -> tuple[int, int] | None:
    """Query the most recent completed successful scheduled run on main. Returns (run_number, run_attempt) or None."""
    res = run_gh_command(
        [
            "run",
            "list",
            "--repo",
            repo,
            "--workflow",
            workflow,
            "--branch",
            branch,
            "--event",
            "schedule",
            "--status",
            "success",
            "--limit",
            "1",
            "--json",
            "number,attempt,conclusion",
        ],
        runner=runner,
    )
    if res.returncode != 0:
        print(f"WARNING: Failed to query latest successful run: {res.stderr.strip()}", file=sys.stderr)
        return None

    try:
        runs = json.loads(res.stdout or "[]")
        if not runs:
            return None
        r = runs[0]
        if r.get("conclusion") == "success":
            return int(r.get("number", 0)), int(r.get("attempt", 1))
    except (json.JSONDecodeError, ValueError, TypeError) as err:
        print(f"WARNING: Failed to parse workflow runs JSON: {err}", file=sys.stderr)
        return None

    return None


def is_run_already_recorded(
    issue_data: dict[str, Any],
    run_id: str,
    run_attempt: str,
) -> bool:
    """Check if the given run_id and run_attempt are already recorded in body or comments."""
    contents: list[str] = []
    if issue_data.get("body"):
        contents.append(issue_data["body"])
    for comment in issue_data.get("comments", []):
        if isinstance(comment, dict) and comment.get("body"):
            contents.append(comment["body"])

    for content in contents:
        for match in METADATA_REGEX.finditer(content):
            try:
                meta = json.loads(match.group(1))
                if (
                    str(meta.get("run_id")) == str(run_id)
                    and str(meta.get("run_attempt", "1")) == str(run_attempt)
                ):
                    return True
            except json.JSONDecodeError:
                continue
    return False


def extract_latest_failure_metadata(issue_data: dict[str, Any]) -> dict[str, Any] | None:
    """Extract metadata from the issue body and comments to determine the latest failure run info."""
    contents: list[str] = []
    if "body" in issue_data and issue_data["body"]:
        contents.append(issue_data["body"])
    for comment in issue_data.get("comments", []):
        if isinstance(comment, dict) and comment.get("body"):
            contents.append(comment["body"])

    latest_meta: dict[str, Any] | None = None
    for content in contents:
        for match in METADATA_REGEX.finditer(content):
            try:
                meta = json.loads(match.group(1))
                if isinstance(meta, dict):
                    if latest_meta is None or meta.get("run_number", 0) >= latest_meta.get(
                        "run_number", 0
                    ):
                        latest_meta = meta
            except json.JSONDecodeError:
                continue

    return latest_meta


def handle_failure(
    repo: str,
    run_id: str,
    run_number: int,
    run_attempt: str,
    commit_sha: str,
    *,
    runner: Callable[..., subprocess.CompletedProcess[str]] | None = None,
) -> int:
    """Handle a failed nightly autotest run by creating or commenting on an incident issue."""
    ensure_label_exists(repo, INCIDENT_LABEL, runner=runner)
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    meta_payload = json.dumps(
        {
            "run_id": str(run_id),
            "run_number": run_number,
            "run_attempt": str(run_attempt),
            "commit_sha": commit_sha,
            "timestamp": now_iso,
        }
    )
    meta_tag = f"<!-- incident-metadata: {meta_payload} -->"

    open_issue = find_open_incident(repo, runner=runner)

    if open_issue:
        issue_number = open_issue["number"]

        if is_run_already_recorded(open_issue, run_id, run_attempt):
            print(
                f"Run {run_id} (attempt {run_attempt}) is already recorded on open incident #{issue_number}. "
                "Skipping duplicate comment."
            )
            return 0

        comment_body = (
            f"### 🚨 Nightly Autotest Run Failed Again\n\n"
            f"- **Run ID:** [{run_id}](https://github.com/{repo}/actions/runs/{run_id}) (attempt {run_attempt})\n"
            f"- **Commit:** `{commit_sha}`\n"
            f"- **Date:** {now_iso}\n"
            f"- **Allure Report:** Download workflow artifact `allure-report` from run [{run_id}](https://github.com/{repo}/actions/runs/{run_id})\n\n"
            f"{meta_tag}"
        )
        res = run_gh_command(
            [
                "issue",
                "comment",
                str(issue_number),
                "--repo",
                repo,
                "--body",
                comment_body,
            ],
            runner=runner,
        )
        if res.returncode != 0:
            print(f"ERROR: Failed to comment on issue #{issue_number}: {res.stderr.strip()}", file=sys.stderr)
            return 1
        print(f"Appended failure comment to existing incident #{issue_number}")
        return 0

    current_attempt = int(run_attempt)

    # No open issue: check if this failure is an outdated rerun after a resolved incident
    latest_closed, res_meta = find_latest_resolved_incident(repo, runner=runner)
    if latest_closed and res_meta:
        resolved_run_num = res_meta.get("resolved_by_run_number", 0)
        resolved_attempt = int(res_meta.get("resolved_by_run_attempt", "1"))
        if (run_number, current_attempt) <= (resolved_run_num, resolved_attempt):
            print(
                f"WARNING: Incoming failure from run #{run_number} (attempt {current_attempt}) is an outdated rerun; "
                f"incident #{latest_closed['number']} was already resolved by run #{resolved_run_num} (attempt {resolved_attempt}). "
                "Skipping new incident creation."
            )
            return 0

    # Also check if a subsequent scheduled run on main has already succeeded
    latest_success = get_latest_successful_scheduled_run(repo, runner=runner)
    if latest_success:
        succ_run_num, succ_attempt = latest_success
        if (run_number, current_attempt) <= (succ_run_num, succ_attempt):
            print(
                f"WARNING: Incoming failure from run #{run_number} (attempt {current_attempt}) is an outdated rerun; "
                f"subsequent scheduled run #{succ_run_num} (attempt {succ_attempt}) has already succeeded on main. "
                "Skipping new incident creation."
            )
            return 0

    # Create new incident issue
    issue_body = (
        f"## 🚨 Nightly Autotest Failure on main\n\n"
        f"Nightly regression autotest suite failed on branch `main`.\n\n"
        f"- **Run ID:** [{run_id}](https://github.com/{repo}/actions/runs/{run_id}) (attempt {run_attempt})\n"
        f"- **Commit:** `{commit_sha}`\n"
        f"- **Date:** {now_iso}\n"
        f"- **Allure Report:** Download workflow artifact `allure-report` from run [{run_id}](https://github.com/{repo}/actions/runs/{run_id})\n\n"
        f"*This incident issue was automatically generated by the isolated `incident-reporter` job.*\n\n"
        f"{meta_tag}"
    )
    res = run_gh_command(
        [
            "issue",
            "create",
            "--repo",
            repo,
            "--title",
            INCIDENT_TITLE,
            "--label",
            f"{INCIDENT_LABEL},bug,DevOps",
            "--body",
            issue_body,
        ],
        runner=runner,
    )
    if res.returncode != 0:
        print(f"ERROR: Failed to create incident issue: {res.stderr.strip()}", file=sys.stderr)
        return 1

    print(f"Created new incident issue: {res.stdout.strip()}")
    return 0


def handle_success(
    repo: str,
    run_id: str,
    run_number: int,
    run_attempt: str,
    commit_sha: str,
    *,
    runner: Callable[..., subprocess.CompletedProcess[str]] | None = None,
) -> int:
    """Handle a successful nightly autotest run by closing any open incident issue."""
    open_issue = find_open_incident(repo, runner=runner)
    if not open_issue:
        print("No open nightly incident found. Nothing to resolve.")
        return 0

    issue_number = open_issue["number"]
    latest_failure = extract_latest_failure_metadata(open_issue)

    current_attempt = int(run_attempt)
    if latest_failure:
        fail_run_num = latest_failure.get("run_number", 0)
        fail_attempt = int(latest_failure.get("run_attempt", "1"))
        if (run_number, current_attempt) < (fail_run_num, fail_attempt):
            print(
                f"WARNING: Current run #{run_number} (attempt {current_attempt}) is an outdated rerun; "
                f"latest failure was run #{fail_run_num} (attempt {fail_attempt}). "
                f"Keeping incident #{issue_number} open."
            )
            return 0

    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    res_payload = json.dumps(
        {
            "resolved_by_run_number": run_number,
            "resolved_by_run_id": str(run_id),
            "resolved_by_run_attempt": str(run_attempt),
            "commit_sha": commit_sha,
            "timestamp": now_iso,
        }
    )
    res_tag = f"<!-- resolution-metadata: {res_payload} -->"

    close_comment = (
        f"### ✅ Nightly Autotest Run Succeeded on main\n\n"
        f"The nightly regression suite passed successfully. Incident resolved automatically.\n\n"
        f"- **Run ID:** [{run_id}](https://github.com/{repo}/actions/runs/{run_id})\n"
        f"- **Commit:** `{commit_sha}`\n"
        f"- **Date:** {now_iso}\n\n"
        f"{res_tag}"
    )

    res = run_gh_command(
        [
            "issue",
            "close",
            str(issue_number),
            "--repo",
            repo,
            "--comment",
            close_comment,
            "--reason",
            "completed",
        ],
        runner=runner,
    )
    if res.returncode != 0:
        print(f"ERROR: Failed to close incident #{issue_number}: {res.stderr.strip()}", file=sys.stderr)
        return 1

    print(f"Successfully closed incident #{issue_number} with resolution comment.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Automated incident reporter for nightly autotest workflow."
    )
    parser.add_argument(
        "--result",
        required=True,
        choices=["success", "failure", "cancelled", "skipped"],
        help="Conclusion status of the autotests job",
    )
    parser.add_argument("--repo", required=True, help="GitHub repository (owner/repo)")
    parser.add_argument("--run-id", required=True, help="GitHub Actions Run ID")
    parser.add_argument("--run-number", type=int, required=True, help="GitHub Actions Run Number")
    parser.add_argument("--run-attempt", default="1", help="GitHub Actions Run Attempt")
    parser.add_argument("--commit-sha", required=True, help="Commit SHA on main")

    args = parser.parse_args(argv)

    if args.result == "failure":
        return handle_failure(
            repo=args.repo,
            run_id=args.run_id,
            run_number=args.run_number,
            run_attempt=args.run_attempt,
            commit_sha=args.commit_sha,
        )
    elif args.result == "success":
        return handle_success(
            repo=args.repo,
            run_id=args.run_id,
            run_number=args.run_number,
            run_attempt=args.run_attempt,
            commit_sha=args.commit_sha,
        )
    else:
        print(f"Autotests result is '{args.result}'. Incident reporter takes no action.")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
