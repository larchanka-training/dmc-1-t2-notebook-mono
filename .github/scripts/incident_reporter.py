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


class IncidentReporterError(Exception):
    """Raised when an operation in incident reporter fails."""


def run_gh_command(
    args: list[str],
    *,
    runner: Callable[[list[str]], subprocess.CompletedProcess[str]] | None = None,
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
    runner: Callable[[list[str]], subprocess.CompletedProcess[str]] | None = None,
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


def find_open_incident(
    repo: str,
    *,
    runner: Callable[[list[str]], subprocess.CompletedProcess[str]] | None = None,
) -> dict[str, Any] | None:
    """Find any open incident issue with the nightly-incident label."""
    res = run_gh_command(
        [
            "issue",
            "list",
            "--repo",
            repo,
            "--state",
            "open",
            "--label",
            INCIDENT_LABEL,
            "--json",
            "number,title,createdAt,body,comments",
        ],
        runner=runner,
    )
    if res.returncode != 0:
        raise IncidentReporterError(f"Failed to query issues: {res.stderr.strip()}")

    try:
        issues = json.loads(res.stdout or "[]")
    except json.JSONDecodeError as err:
        raise IncidentReporterError(f"Failed to parse issue list JSON: {err}")

    if not issues:
        return None

    # Return the first matching open incident
    return issues[0]


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
    runner: Callable[[list[str]], subprocess.CompletedProcess[str]] | None = None,
) -> int:
    """Handle a failed nightly autotest run by creating or commenting on an incident issue."""
    ensure_label_exists(repo, INCIDENT_LABEL, runner=runner)
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    meta_payload = json.dumps(
        {
            "run_id": run_id,
            "run_number": run_number,
            "run_attempt": run_attempt,
            "commit_sha": commit_sha,
            "timestamp": now_iso,
        }
    )
    meta_tag = f"<!-- incident-metadata: {meta_payload} -->"

    open_issue = find_open_incident(repo, runner=runner)

    if open_issue:
        issue_number = open_issue["number"]
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
    runner: Callable[[list[str]], subprocess.CompletedProcess[str]] | None = None,
) -> int:
    """Handle a successful nightly autotest run by closing any open incident issue."""
    open_issue = find_open_incident(repo, runner=runner)
    if not open_issue:
        print("No open nightly incident found. Nothing to resolve.")
        return 0

    issue_number = open_issue["number"]
    latest_failure = extract_latest_failure_metadata(open_issue)

    if latest_failure and run_number < latest_failure.get("run_number", 0):
        print(
            f"WARNING: Current run #{run_number} is an outdated rerun; "
            f"latest failure was run #{latest_failure.get('run_number')}. "
            f"Keeping incident #{issue_number} open."
        )
        return 0

    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    close_comment = (
        f"### ✅ Nightly Autotest Run Succeeded on main\n\n"
        f"The nightly regression suite passed successfully. Incident resolved automatically.\n\n"
        f"- **Run ID:** [{run_id}](https://github.com/{repo}/actions/runs/{run_id})\n"
        f"- **Commit:** `{commit_sha}`\n"
        f"- **Date:** {now_iso}\n"
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
