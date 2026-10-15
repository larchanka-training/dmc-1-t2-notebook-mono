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
        create_call = next(c for c in commands_run if "issue" in c and "create" in c)
        self.assertIn("--title", create_call)
        self.assertIn(incident_reporter.INCIDENT_TITLE, create_call)
        self.assertIn("nightly-incident,bug,DevOps", create_call)
        body_idx = create_call.index("--body") + 1
        body = create_call[body_idx]
        self.assertIn("<!-- incident-metadata:", body)
        self.assertIn('"run_number": 10', body)

    def test_handle_failure_comments_on_existing_issue(self) -> None:
        commands_run: list[list[str]] = []
        existing = {"number": 42, "title": incident_reporter.INCIDENT_TITLE, "body": "", "comments": []}

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

    def test_handle_failure_deduplicates_identical_run_attempt(self) -> None:
        commands_run: list[list[str]] = []
        meta = json.dumps({"run_id": "12346", "run_attempt": "1", "run_number": 11})
        existing = {
            "number": 42,
            "title": incident_reporter.INCIDENT_TITLE,
            "body": f"Initial <!-- incident-metadata: {meta} -->",
            "comments": [],
        }

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
        comment_calls = [c for c in commands_run if "issue" in c and "comment" in c]
        self.assertEqual(len(comment_calls), 0, "Duplicate run_id and attempt must be skipped")

    def test_handle_failure_skips_outdated_failed_rerun_after_resolution(self) -> None:
        commands_run: list[list[str]] = []
        res_meta = json.dumps({"resolved_by_run_number": 11, "resolved_by_run_id": "999"})
        closed_incident = {
            "number": 40,
            "state": "closed",
            "body": "Closed incident",
            "comments": [{"body": f"Resolved <!-- resolution-metadata: {res_meta} -->"}],
        }

        def fake_runner(cmd: list[str], *args, **kwargs) -> FakeProcess:
            commands_run.append(cmd)
            if "issue" in cmd and "list" in cmd:
                if "open" in cmd:
                    return FakeProcess(0, "[]", "")
                if "closed" in cmd:
                    return FakeProcess(0, json.dumps([closed_incident]), "")
            return FakeProcess(0, "", "")

        # Rerun of failure #10 arrives after run #11 already resolved incident #40
        ret = incident_reporter.handle_failure(
            repo="org/repo",
            run_id="12345",
            run_number=10,
            run_attempt="2",
            commit_sha="oldcommit",
            runner=fake_runner,
        )
        self.assertEqual(ret, 0)
        create_calls = [c for c in commands_run if "issue" in c and "create" in c]
        self.assertEqual(len(create_calls), 0, "Outdated failed rerun after resolution must not create new issue")

    def test_handle_failure_creates_new_issue_if_failure_is_newer_than_resolution(self) -> None:
        commands_run: list[list[str]] = []
        res_meta = json.dumps({"resolved_by_run_number": 11, "resolved_by_run_id": "999"})
        closed_incident = {
            "number": 40,
            "state": "closed",
            "body": "Closed incident",
            "comments": [{"body": f"Resolved <!-- resolution-metadata: {res_meta} -->"}],
        }

        def fake_runner(cmd: list[str], *args, **kwargs) -> FakeProcess:
            commands_run.append(cmd)
            if "issue" in cmd and "list" in cmd:
                if "open" in cmd:
                    return FakeProcess(0, "[]", "")
                if "closed" in cmd:
                    return FakeProcess(0, json.dumps([closed_incident]), "")
            return FakeProcess(0, "https://github.com/org/repo/issues/101", "")

        # New failure at run #12 arrives after resolution at run #11
        ret = incident_reporter.handle_failure(
            repo="org/repo",
            run_id="22222",
            run_number=12,
            run_attempt="1",
            commit_sha="newcommit",
            runner=fake_runner,
        )
        self.assertEqual(ret, 0)
        create_calls = [c for c in commands_run if "issue" in c and "create" in c]
        self.assertEqual(len(create_calls), 1, "New failure after resolution must create new incident")

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
        comment_idx = close_call.index("--comment") + 1
        self.assertIn("<!-- resolution-metadata:", close_call[comment_idx])

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
    def test_handle_failure_creates_new_issue_on_newer_attempt_of_same_run(self) -> None:
        commands_run: list[list[str]] = []
        res_meta = json.dumps({"resolved_by_run_number": 10, "resolved_by_run_attempt": "2"})
        closed_incident = {
            "number": 40,
            "state": "closed",
            "body": "Closed incident",
            "comments": [{"body": f"Resolved <!-- resolution-metadata: {res_meta} -->"}],
        }

        def fake_runner(cmd: list[str], *args, **kwargs) -> FakeProcess:
            commands_run.append(cmd)
            if "issue" in cmd and "list" in cmd:
                if "open" in cmd:
                    return FakeProcess(0, "[]", "")
                if "closed" in cmd:
                    return FakeProcess(0, json.dumps([closed_incident]), "")
            if "run" in cmd and "list" in cmd:
                return FakeProcess(0, "[]", "")
            return FakeProcess(0, "https://github.com/org/repo/issues/102", "")

        # Attempt 3 failed after attempt 2 had succeeded
        ret = incident_reporter.handle_failure(
            repo="org/repo",
            run_id="12345",
            run_number=10,
            run_attempt="3",
            commit_sha="retrycommit",
            runner=fake_runner,
        )
        self.assertEqual(ret, 0)
        create_calls = [c for c in commands_run if "issue" in c and "create" in c]
        self.assertEqual(len(create_calls), 1, "Newer attempt of same run must create new incident")

    def test_handle_failure_skips_outdated_rerun_when_actions_history_has_subsequent_success(self) -> None:
        commands_run: list[list[str]] = []
        actions_runs = [
            {"number": 11, "attempt": 1, "conclusion": "success"},
            {"number": 10, "attempt": 1, "conclusion": "success"},
        ]

        def fake_runner(cmd: list[str], *args, **kwargs) -> FakeProcess:
            commands_run.append(cmd)
            if "issue" in cmd and "list" in cmd:
                return FakeProcess(0, "[]", "")
            if "run" in cmd and "list" in cmd:
                return FakeProcess(0, json.dumps(actions_runs), "")
            return FakeProcess(0, "", "")

        # Rerun of run 10 attempt 2 fails after run 11 already succeeded
        ret = incident_reporter.handle_failure(
            repo="org/repo",
            run_id="12345",
            run_number=10,
            run_attempt="2",
            commit_sha="oldcommit",
            runner=fake_runner,
        )
        self.assertEqual(ret, 0)
        create_calls = [c for c in commands_run if "issue" in c and "create" in c]
        self.assertEqual(len(create_calls), 0, "Outdated failure when actions history has newer success must be skipped")

    def test_handle_failure_creates_issue_when_failure_is_newer_than_actions_history(self) -> None:
        commands_run: list[list[str]] = []
        actions_runs = [
            {"number": 11, "attempt": 1, "conclusion": "success"},
        ]

        def fake_runner(cmd: list[str], *args, **kwargs) -> FakeProcess:
            commands_run.append(cmd)
            if "issue" in cmd and "list" in cmd:
                return FakeProcess(0, "[]", "")
            if "run" in cmd and "list" in cmd:
                return FakeProcess(0, json.dumps(actions_runs), "")
            return FakeProcess(0, "https://github.com/org/repo/issues/103", "")

        # Run 12 attempt 1 fails after run 11 succeeded
        ret = incident_reporter.handle_failure(
            repo="org/repo",
            run_id="99999",
            run_number=12,
            run_attempt="1",
            commit_sha="newcommit",
            runner=fake_runner,
        )
        self.assertEqual(ret, 0)
        create_calls = [c for c in commands_run if "issue" in c and "create" in c]
        self.assertEqual(len(create_calls), 1, "New failure after latest successful action must create new incident")

    def test_handle_failure_skips_outdated_rerun_when_success_is_preceded_by_many_cancelled_runs(self) -> None:
        """Verify that CLI query filters by --status success so intermediate cancelled runs do not truncate the success."""
        commands_run: list[list[str]] = []
        successful_runs = [
            {"number": 11, "attempt": 1, "conclusion": "success"},
        ]

        def fake_runner(cmd: list[str], *args, **kwargs) -> FakeProcess:
            commands_run.append(cmd)
            if "issue" in cmd and "list" in cmd:
                return FakeProcess(0, "[]", "")
            if "run" in cmd and "list" in cmd:
                self.assertIn("--status", cmd)
                self.assertIn("success", cmd)
                self.assertIn("--limit", cmd)
                self.assertIn("1", cmd)
                return FakeProcess(0, json.dumps(successful_runs), "")
            return FakeProcess(0, "", "")

        # Rerun 10 attempt 2 arrives after run 11 succeeded (even if runs 12-16 were cancelled)
        ret = incident_reporter.handle_failure(
            repo="org/repo",
            run_id="12345",
            run_number=10,
            run_attempt="2",
            commit_sha="oldcommit",
            runner=fake_runner,
        )
        self.assertEqual(ret, 0)
        create_calls = [c for c in commands_run if "issue" in c and "create" in c]
        self.assertEqual(len(create_calls), 0, "Outdated rerun must be skipped because run 11 succeeded")

    def test_handle_failure_creates_issue_when_actions_query_fails(self) -> None:
        commands_run: list[list[str]] = []

        def fake_runner(cmd: list[str], *args, **kwargs) -> FakeProcess:
            commands_run.append(cmd)
            if "issue" in cmd and "list" in cmd:
                return FakeProcess(0, "[]", "")
            if "run" in cmd and "list" in cmd:
                return FakeProcess(1, "", "API error")
            return FakeProcess(0, "https://github.com/org/repo/issues/104", "")

        ret = incident_reporter.handle_failure(
            repo="org/repo",
            run_id="99999",
            run_number=12,
            run_attempt="1",
            commit_sha="newcommit",
            runner=fake_runner,
        )
        self.assertEqual(ret, 0)
        create_calls = [c for c in commands_run if "issue" in c and "create" in c]
        self.assertEqual(len(create_calls), 1, "Failure should still create issue if actions query fails")


if __name__ == "__main__":
    unittest.main()
