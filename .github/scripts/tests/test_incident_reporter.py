from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import incident_reporter  # noqa: E402


class FakeProcess:
    def __init__(self, returncode: int = 0, stdout: str = "", stderr: str = ""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


class IncidentReporterTests(unittest.TestCase):
    def test_ensure_label_exists_calls_gh(self) -> None:
        calls: list[list[str]] = []

        def fake_runner(cmd: list[str], *args, **kwargs) -> FakeProcess:
            calls.append(cmd)
            return FakeProcess(0, "", "")

        incident_reporter.ensure_label_exists("org/repo", "nightly-incident", runner=fake_runner)
        self.assertEqual(len(calls), 1)
        self.assertIn("label", calls[0])
        self.assertIn("create", calls[0])
        self.assertIn("nightly-incident", calls[0])

    def test_find_open_incident_returns_none_when_empty(self) -> None:
        def fake_runner(cmd: list[str], *args, **kwargs) -> FakeProcess:
            return FakeProcess(0, "[]", "")

        res = incident_reporter.find_open_incident("org/repo", runner=fake_runner)
        self.assertIsNone(res)

    def test_find_open_incident_returns_first_issue(self) -> None:
        issue = {"number": 42, "title": "🚨 Nightly Autotest Failure on main"}

        def fake_runner(cmd: list[str], *args, **kwargs) -> FakeProcess:
            return FakeProcess(0, json.dumps([issue]), "")

        res = incident_reporter.find_open_incident("org/repo", runner=fake_runner)
        self.assertEqual(res, issue)

    def test_handle_failure_creates_new_issue_when_none_open(self) -> None:
        commands_run: list[list[str]] = []

        def fake_runner(cmd: list[str], *args, **kwargs) -> FakeProcess:
            commands_run.append(cmd)
            if "issue" in cmd and "list" in cmd:
                return FakeProcess(0, "[]", "")
            return FakeProcess(0, "https://github.com/org/repo/issues/100", "")

        ret = incident_reporter.handle_failure(
            repo="org/repo",
            run_id="12345",
            run_number=10,
            run_attempt="1",
            commit_sha="abcdef1",
            runner=fake_runner,
        )
        self.assertEqual(ret, 0)
        # Should have called label create, issue list, and issue create
        create_call = next(c for c in commands_run if "issue" in c and "create" in c)
        self.assertIn("--title", create_call)
        self.assertIn(incident_reporter.INCIDENT_TITLE, create_call)
        self.assertIn("nightly-incident,bug,DevOps", create_call)
        # Verify metadata is embedded
        body_idx = create_call.index("--body") + 1
        body = create_call[body_idx]
        self.assertIn("<!-- incident-metadata:", body)
        self.assertIn('"run_number": 10', body)

    def test_handle_failure_comments_on_existing_issue(self) -> None:
        commands_run: list[list[str]] = []
        existing = {"number": 42, "title": incident_reporter.INCIDENT_TITLE}

        def fake_runner(cmd: list[str], *args, **kwargs) -> FakeProcess:
            commands_run.append(cmd)
            if "issue" in cmd and "list" in cmd:
                return FakeProcess(0, json.dumps([existing]), "")
            return FakeProcess(0, "", "")

        ret = incident_reporter.handle_failure(
            repo="org/repo",
            run_id="12346",
            run_number=11,
            run_attempt="1",
            commit_sha="abcdef2",
            runner=fake_runner,
        )
        self.assertEqual(ret, 0)
        comment_call = next(c for c in commands_run if "issue" in c and "comment" in c)
        self.assertIn("42", comment_call)
        body_idx = comment_call.index("--body") + 1
        body = comment_call[body_idx]
        self.assertIn("🚨 Nightly Autotest Run Failed Again", body)
        self.assertIn('"run_number": 11', body)

    def test_handle_success_closes_existing_issue_when_newer(self) -> None:
        commands_run: list[list[str]] = []
        meta = json.dumps({"run_number": 10, "run_id": "12345"})
        existing = {
            "number": 42,
            "title": incident_reporter.INCIDENT_TITLE,
            "body": f"Some body <!-- incident-metadata: {meta} -->",
            "comments": [],
        }

        def fake_runner(cmd: list[str], *args, **kwargs) -> FakeProcess:
            commands_run.append(cmd)
            if "issue" in cmd and "list" in cmd:
                return FakeProcess(0, json.dumps([existing]), "")
            return FakeProcess(0, "", "")

        ret = incident_reporter.handle_success(
            repo="org/repo",
            run_id="12347",
            run_number=11,
            run_attempt="1",
            commit_sha="abcdef3",
            runner=fake_runner,
        )
        self.assertEqual(ret, 0)
        close_call = next(c for c in commands_run if "issue" in c and "close" in c)
        self.assertIn("42", close_call)
        self.assertIn("--reason", close_call)
        self.assertIn("completed", close_call)

    def test_handle_success_does_not_close_when_outdated_rerun(self) -> None:
        commands_run: list[list[str]] = []
        meta = json.dumps({"run_number": 15, "run_id": "99999"})
        existing = {
            "number": 42,
            "title": incident_reporter.INCIDENT_TITLE,
            "body": f"Failure <!-- incident-metadata: {meta} -->",
            "comments": [],
        }

        def fake_runner(cmd: list[str], *args, **kwargs) -> FakeProcess:
            commands_run.append(cmd)
            if "issue" in cmd and "list" in cmd:
                return FakeProcess(0, json.dumps([existing]), "")
            return FakeProcess(0, "", "")

        # Current run is 12, but latest failure was run 15 (older rerun!)
        ret = incident_reporter.handle_success(
            repo="org/repo",
            run_id="10000",
            run_number=12,
            run_attempt="1",
            commit_sha="abcdef0",
            runner=fake_runner,
        )
        self.assertEqual(ret, 0)
        close_calls = [c for c in commands_run if "issue" in c and "close" in c]
        self.assertEqual(len(close_calls), 0, "Outdated rerun should not close active incident")

    def test_handle_success_noop_when_no_open_issue(self) -> None:
        commands_run: list[list[str]] = []

        def fake_runner(cmd: list[str], *args, **kwargs) -> FakeProcess:
            commands_run.append(cmd)
            return FakeProcess(0, "[]", "")

        ret = incident_reporter.handle_success(
            repo="org/repo",
            run_id="12347",
            run_number=11,
            run_attempt="1",
            commit_sha="abcdef3",
            runner=fake_runner,
        )
        self.assertEqual(ret, 0)
        close_calls = [c for c in commands_run if "issue" in c and "close" in c]
        self.assertEqual(len(close_calls), 0)

    def test_main_cli_dispatch(self) -> None:
        ret = incident_reporter.main(
            [
                "--result",
                "cancelled",
                "--repo",
                "org/repo",
                "--run-id",
                "123",
                "--run-number",
                "1",
                "--commit-sha",
                "abc",
            ]
        )
        self.assertEqual(ret, 0)


if __name__ == "__main__":
    unittest.main()
