#!/usr/bin/env python3
"""
Unit and functional tests for Aeza backup and restore verification scripts:
- scripts/backup-aeza.sh
- scripts/restore-disposable-db.sh
"""

import hashlib
import os
import re
import shutil
import stat
import subprocess
import tempfile
import unittest
import uuid
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
SCRIPTS_DIR = PROJECT_ROOT / "scripts"
BACKUP_SCRIPT = SCRIPTS_DIR / "backup-aeza.sh"
RESTORE_SCRIPT = SCRIPTS_DIR / "restore-disposable-db.sh"


class TestBackupScriptsSyntax(unittest.TestCase):
    """Verify that all bash scripts pass bash -n syntax checks."""

    def test_backup_script_syntax(self):
        self.assertTrue(BACKUP_SCRIPT.is_file(), f"{BACKUP_SCRIPT} does not exist")
        res = subprocess.run(["bash", "-n", str(BACKUP_SCRIPT)], capture_output=True, text=True)
        self.assertEqual(res.returncode, 0, f"bash -n failed for {BACKUP_SCRIPT}: {res.stderr}")

    def test_restore_script_syntax(self):
        self.assertTrue(RESTORE_SCRIPT.is_file(), f"{RESTORE_SCRIPT} does not exist")
        res = subprocess.run(["bash", "-n", str(RESTORE_SCRIPT)], capture_output=True, text=True)
        self.assertEqual(res.returncode, 0, f"bash -n failed for {RESTORE_SCRIPT}: {res.stderr}")


class TestBackupAezaCli(unittest.TestCase):
    """Test CLI behavior, flags, and guard conditions for backup-aeza.sh."""

    def test_help_flag(self):
        res = subprocess.run([str(BACKUP_SCRIPT), "--help"], capture_output=True, text=True)
        self.assertEqual(res.returncode, 0)
        self.assertIn("Usage:", res.stdout)
        self.assertIn("--dry-run", res.stdout)
        self.assertIn("--skip-hostname-check", res.stdout)

    def test_hostname_check_fails_on_non_aeza(self):
        """Unless --skip-hostname-check is passed, running on non-fortunate-pink should fail."""
        with tempfile.TemporaryDirectory() as tmpdir:
            res = subprocess.run(
                [str(BACKUP_SCRIPT), "--backup-root", tmpdir],
                capture_output=True,
                text=True,
            )
            current_host = os.uname().nodename
            if current_host != "fortunate-pink":
                self.assertEqual(res.returncode, 1)
                self.assertIn("Host check failed", res.stderr)

    def test_dry_run_success_with_skip_hostname(self):
        """With skip-hostname-check, valid env and compose files, dry-run succeeds."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            env_file = tmp_path / ".env.prod"
            env_file.write_text("POSTGRES_USER=wiki\nPOSTGRES_DB=wiki\n")
            os.chmod(env_file, 0o600)

            compose_file = tmp_path / "docker-compose.prod.yaml"
            compose_file.write_text("services: {}\n")

            backup_root = tmp_path / "backups"

            res = subprocess.run(
                [
                    str(BACKUP_SCRIPT),
                    "--dry-run",
                    "--skip-hostname-check",
                    "--env-file", str(env_file),
                    "--compose-file", str(compose_file),
                    "--backup-root", str(backup_root),
                ],
                capture_output=True,
                text=True,
            )
            self.assertEqual(res.returncode, 0, f"Dry-run failed: {res.stderr}\n{res.stdout}")
            self.assertIn("DRY_RUN: Pre-flight checks passed successfully", res.stdout)

    def test_env_file_loose_permissions_fails_closed(self):
        """If env file has loose permissions (e.g. 0644), script must fail closed."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            env_file = tmp_path / ".env.prod"
            env_file.write_text("POSTGRES_USER=wiki\nPOSTGRES_DB=wiki\n")
            os.chmod(env_file, 0o644)

            compose_file = tmp_path / "docker-compose.prod.yaml"
            compose_file.write_text("services: {}\n")

            res = subprocess.run(
                [
                    str(BACKUP_SCRIPT),
                    "--dry-run",
                    "--skip-hostname-check",
                    "--env-file", str(env_file),
                    "--compose-file", str(compose_file),
                    "--backup-root", str(tmp_path / "backups"),
                ],
                capture_output=True,
                text=True,
            )
            self.assertEqual(res.returncode, 1)
            self.assertIn("refusing to proceed", res.stderr)

    def test_disk_space_guard(self):
        """If min-free-kb is set unrealistically high, backup script must fail closed."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            env_file = tmp_path / ".env.prod"
            env_file.write_text("POSTGRES_USER=wiki\nPOSTGRES_DB=wiki\n")
            os.chmod(env_file, 0o600)

            compose_file = tmp_path / "docker-compose.prod.yaml"
            compose_file.write_text("services: {}\n")

            res = subprocess.run(
                [
                    str(BACKUP_SCRIPT),
                    "--dry-run",
                    "--skip-hostname-check",
                    "--env-file", str(env_file),
                    "--compose-file", str(compose_file),
                    "--backup-root", str(tmp_path / "backups"),
                    "--min-free-kb", "999999999999",  # Absurdly high
                ],
                capture_output=True,
                text=True,
            )
            self.assertEqual(res.returncode, 1)
            self.assertIn("Insufficient disk space", res.stderr)

    def test_missing_env_file_fails(self):
        """Missing env file fails closed."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            compose_file = tmp_path / "docker-compose.prod.yaml"
            compose_file.write_text("services: {}\n")

            res = subprocess.run(
                [
                    str(BACKUP_SCRIPT),
                    "--dry-run",
                    "--skip-hostname-check",
                    "--env-file", str(tmp_path / "nonexistent.env"),
                    "--compose-file", str(compose_file),
                    "--backup-root", str(tmp_path / "backups"),
                ],
                capture_output=True,
                text=True,
            )
            self.assertEqual(res.returncode, 1)
            self.assertIn("Environment file", res.stderr)

    def test_encryption_requested_without_tools_fails_closed(self):
        """Requesting encryption when neither age nor gpg is on PATH must fail closed."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            env_file = tmp_path / ".env.prod"
            env_file.write_text("POSTGRES_USER=wiki\nPOSTGRES_DB=wiki\n")
            os.chmod(env_file, 0o600)

            compose_file = tmp_path / "docker-compose.prod.yaml"
            compose_file.write_text("services: {}\n")

            # Create controlled bindir with standard utilities excluding age and gpg
            bindir = tmp_path / "clean_bin"
            bindir.mkdir()
            for tool in (
                "bash", "sh", "date", "uname", "hostname", "grep", "sed", "awk",
                "mktemp", "chmod", "df", "cat", "rm", "mkdir", "install", "test",
                "basename", "dirname", "cut", "tr", "id", "stat", "docker"
            ):
                tool_path = shutil.which(tool)
                if tool_path:
                    (bindir / tool).symlink_to(tool_path)

            custom_env = os.environ.copy()
            custom_env["PATH"] = str(bindir)

            res = subprocess.run(
                [
                    str(BACKUP_SCRIPT),
                    "--dry-run",
                    "--skip-hostname-check",
                    "--env-file", str(env_file),
                    "--compose-file", str(compose_file),
                    "--backup-root", str(tmp_path / "backups"),
                    "--encrypt-recipient", "age1dummykey12345",
                ],
                capture_output=True,
                text=True,
                env=custom_env,
            )
            self.assertEqual(res.returncode, 1)
            self.assertIn("neither 'age' nor 'gpg' was found in PATH", res.stderr)


class TestRestoreDisposableDbCli(unittest.TestCase):
    """Test CLI behavior and validation for restore-disposable-db.sh."""

    def test_help_flag(self):
        res = subprocess.run([str(RESTORE_SCRIPT), "--help"], capture_output=True, text=True)
        self.assertEqual(res.returncode, 0)
        self.assertIn("Usage:", res.stdout)
        self.assertIn("--keep-on-failure", res.stdout)
        self.assertIn("--allow-missing-row-counts", res.stdout)
        self.assertIn("--dry-run", res.stdout)

    def test_missing_target_argument(self):
        res = subprocess.run([str(RESTORE_SCRIPT)], capture_output=True, text=True)
        self.assertEqual(res.returncode, 1)
        self.assertIn("Path to database.dump or backup directory is required", res.stderr)

    def test_nonexistent_target_fails(self):
        res = subprocess.run(
            [str(RESTORE_SCRIPT), "/nonexistent/path/to/dump"],
            capture_output=True,
            text=True,
        )
        self.assertEqual(res.returncode, 1)
        self.assertIn("does not exist", res.stderr)

    def test_empty_dump_fails(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            empty_dump = Path(tmpdir) / "database.dump"
            empty_dump.write_bytes(b"")
            res = subprocess.run([str(RESTORE_SCRIPT), str(empty_dump)], capture_output=True, text=True)
            self.assertEqual(res.returncode, 1)
            self.assertIn("is empty", res.stderr)

    def test_encrypted_dump_passed_directly_fails_closed(self):
        """Passing database.dump.age or .enc directly must fail closed instructing operator to decrypt."""
        with tempfile.TemporaryDirectory() as tmpdir:
            enc_file = Path(tmpdir) / "database.dump.age"
            enc_file.write_bytes(b"encrypted_content_bytes")
            res = subprocess.run([str(RESTORE_SCRIPT), str(enc_file)], capture_output=True, text=True)
            self.assertEqual(res.returncode, 1)
            self.assertIn("Decrypt the file first", res.stderr)

    def test_encrypted_dir_without_plaintext_fails_closed(self):
        """Passing directory with encrypted dump but no decrypted dump must fail closed."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            enc_file = tmp_path / "database.dump.age"
            enc_file.write_bytes(b"encrypted_content_bytes")
            res = subprocess.run([str(RESTORE_SCRIPT), str(tmp_path)], capture_output=True, text=True)
            self.assertEqual(res.returncode, 1)
            self.assertIn("contains an encrypted archive but no decrypted", res.stderr)

    def test_missing_row_counts_fails_closed_by_default(self):
        """Without row-counts.txt, restore script must fail closed unless flag is passed."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            dump_file = tmp_path / "database.dump"
            dump_file.write_bytes(b"PGDMP\x01\x0f\x00\x00\x00dummy")

            res = subprocess.run(
                [str(RESTORE_SCRIPT), "--dry-run", str(tmp_path)],
                capture_output=True,
                text=True,
            )
            self.assertEqual(res.returncode, 1)
            self.assertIn("Required metadata 'row-counts.txt' not found", res.stderr)

    def test_dry_run_with_valid_checksum_and_row_counts(self):
        """Test that dry-run passes when checksum and row-counts.txt exist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            dump_file = tmp_path / "database.dump"
            content = b"PGDMP\x01\x0f\x00\x00\x00sample_mock_dump_data"
            dump_file.write_bytes(content)

            row_counts_file = tmp_path / "row-counts.txt"
            row_counts_file.write_text("users.users\t5\npublic.databasechangelog\t8\n")

            sha = hashlib.sha256(content).hexdigest()
            sums_file = tmp_path / "SHA256SUMS"
            sums_file.write_text(f"{sha}  database.dump\n")

            res = subprocess.run(
                [str(RESTORE_SCRIPT), "--dry-run", str(tmp_path)],
                capture_output=True,
                text=True,
            )
            self.assertEqual(res.returncode, 0, f"Expected success in dry run: {res.stderr}\n{res.stdout}")
            self.assertIn("Checksum verification: OK", res.stdout)
            self.assertIn("DRY_RUN: Pre-flight checks passed", res.stdout)

    def test_allow_missing_row_counts_flag(self):
        """With --allow-missing-row-counts, dry-run succeeds even without row-counts.txt."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            dump_file = tmp_path / "database.dump"
            dump_file.write_bytes(b"PGDMP\x01\x0f\x00\x00\x00sample_mock_dump_data")

            res = subprocess.run(
                [str(RESTORE_SCRIPT), "--dry-run", "--allow-missing-row-counts", str(tmp_path)],
                capture_output=True,
                text=True,
            )
            self.assertEqual(res.returncode, 0, f"Expected success: {res.stderr}\n{res.stdout}")
            self.assertIn("DRY_RUN: Pre-flight checks passed", res.stdout)

    def test_checksum_mismatch_fails(self):
        """Test that checksum mismatch fails execution."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            dump_file = tmp_path / "database.dump"
            dump_file.write_bytes(b"corrupted content")

            row_counts_file = tmp_path / "row-counts.txt"
            row_counts_file.write_text("users.users\t5\n")

            sums_file = tmp_path / "SHA256SUMS"
            sums_file.write_text("0000000000000000000000000000000000000000000000000000000000000000  database.dump\n")

            res = subprocess.run(
                [str(RESTORE_SCRIPT), "--dry-run", str(tmp_path)],
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(res.returncode, 0)


class TestRestoreDisposableDbRowCountsVerification(unittest.TestCase):
    """Integration tests for restore-disposable-db.sh verification logic using a mock docker CLI."""

    def _setup_mock_env(self, tmpdir: str, restored_counts: str, lock_status: str = "f") -> tuple[dict[str, str], Path]:
        tmp_path = Path(tmpdir)
        bindir = tmp_path / "mock_bin"
        bindir.mkdir(parents=True, exist_ok=True)

        for tool in (
            "bash", "sh", "date", "uname", "hostname", "grep", "sed", "awk",
            "mktemp", "chmod", "df", "cat", "rm", "mkdir", "install", "test",
            "basename", "dirname", "cut", "tr", "id", "stat", "diff", "python3",
            "head", "seq", "sleep"
        ):
            tool_path = shutil.which(tool)
            if tool_path:
                (bindir / tool).symlink_to(tool_path)

        mock_docker = bindir / "docker"
        mock_docker.write_text("""#!/usr/bin/env python3
import sys, os

args = sys.argv[1:]

if "volume" in args and "create" in args:
    print("mock-volume")
    sys.exit(0)

if "volume" in args and "rm" in args:
    sys.exit(0)

if "rm" in args:
    sys.exit(0)

if "run" in args:
    if "-d" in args:
        print("mock-container-id")
        sys.exit(0)
    sys.exit(0)

if "exec" in args:
    if "pg_isready" in args:
        sys.exit(0)
    if "pg_restore" in args:
        sys.exit(0)
    if "psql" in args:
        cmd_str = " ".join(args)
        if "databasechangeloglock" in cmd_str and "SELECT locked" in cmd_str:
            lock_val = os.environ.get("MOCK_DOCKER_LOCK_STATUS", "f")
            print(lock_val)
            sys.exit(0)
        counts = os.environ.get("MOCK_DOCKER_RESTORED_COUNTS", "")
        print(counts, end="")
        sys.exit(0)

sys.exit(0)
""")
        mock_docker.chmod(0o755)

        custom_env = os.environ.copy()
        custom_env["PATH"] = str(bindir) + ":" + os.environ.get("PATH", "")
        custom_env["MOCK_DOCKER_RESTORED_COUNTS"] = restored_counts
        custom_env["MOCK_DOCKER_LOCK_STATUS"] = lock_status

        dump_dir = tmp_path / "backup_sample"
        dump_dir.mkdir(parents=True, exist_ok=True)
        dump_file = dump_dir / "database.dump"
        dump_file.write_bytes(b"PGDMP_MOCK_ARCHIVE_DATA")

        return custom_env, dump_dir

    def test_restore_exact_match_success(self):
        """When restored row counts match expected snapshot exactly, restore verification succeeds."""
        expected_counts = (
            "notebooks.notebooks\t8\n"
            "public.databasechangelog\t8\n"
            "public.databasechangeloglock\t1\n"
            "users.users\t5\n"
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            custom_env, dump_dir = self._setup_mock_env(tmpdir, expected_counts)
            (dump_dir / "row-counts.txt").write_text(expected_counts)

            res = subprocess.run(
                [str(RESTORE_SCRIPT), str(dump_dir)],
                capture_output=True,
                text=True,
                env=custom_env,
            )
            self.assertEqual(res.returncode, 0, f"Expected success: {res.stderr}\n{res.stdout}")
            self.assertIn("Row count equivalence: OK", res.stdout)
            self.assertIn("RESTORE_VERIFICATION_OK", res.stdout)

    def test_restore_count_discrepancy_fails_closed(self):
        """When table row count differs between snapshot and restored data, script fails closed with diff."""
        expected_counts = (
            "notebooks.notebooks\t8\n"
            "public.databasechangelog\t8\n"
            "public.databasechangeloglock\t1\n"
            "users.users\t5\n"
        )
        # Deliberate count discrepancy on users.users (3 instead of 5)
        restored_counts = (
            "notebooks.notebooks\t8\n"
            "public.databasechangelog\t8\n"
            "public.databasechangeloglock\t1\n"
            "users.users\t3\n"
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            custom_env, dump_dir = self._setup_mock_env(tmpdir, restored_counts)
            (dump_dir / "row-counts.txt").write_text(expected_counts)

            res = subprocess.run(
                [str(RESTORE_SCRIPT), str(dump_dir)],
                capture_output=True,
                text=True,
                env=custom_env,
            )
            self.assertEqual(res.returncode, 1)
            self.assertIn("Row count mismatch between expected snapshot and restored database!", res.stderr)
            self.assertIn("-users.users\t5", res.stdout)
            self.assertIn("+users.users\t3", res.stdout)

    def test_restore_missing_table_fails_closed(self):
        """When a table from snapshot is missing in restored database, script fails closed."""
        expected_counts = (
            "notebooks.notebooks\t8\n"
            "public.databasechangelog\t8\n"
            "public.databasechangeloglock\t1\n"
            "users.users\t5\n"
        )
        restored_counts = (
            "notebooks.notebooks\t8\n"
            "public.databasechangelog\t8\n"
            "public.databasechangeloglock\t1\n"
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            custom_env, dump_dir = self._setup_mock_env(tmpdir, restored_counts)
            (dump_dir / "row-counts.txt").write_text(expected_counts)

            res = subprocess.run(
                [str(RESTORE_SCRIPT), str(dump_dir)],
                capture_output=True,
                text=True,
                env=custom_env,
            )
            self.assertEqual(res.returncode, 1)
            self.assertIn("Row count mismatch", res.stderr)

    def test_restore_unexpected_table_fails_closed(self):
        """When an unexpected table is present in restored database, diff mismatch fails closed."""
        expected_counts = (
            "public.databasechangelog\t8\n"
            "public.databasechangeloglock\t1\n"
            "users.users\t5\n"
        )
        restored_counts = (
            "notebooks.unexpected\t1\n"
            "public.databasechangelog\t8\n"
            "public.databasechangeloglock\t1\n"
            "users.users\t5\n"
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            custom_env, dump_dir = self._setup_mock_env(tmpdir, restored_counts)
            (dump_dir / "row-counts.txt").write_text(expected_counts)

            res = subprocess.run(
                [str(RESTORE_SCRIPT), str(dump_dir)],
                capture_output=True,
                text=True,
                env=custom_env,
            )
            self.assertEqual(res.returncode, 1)
            self.assertIn("Row count mismatch", res.stderr)

    def test_restore_core_table_zero_users_fails_closed(self):
        """When users.users has 0 rows (even if expected), core table assertion fails closed."""
        zero_user_counts = (
            "notebooks.notebooks\t8\n"
            "public.databasechangelog\t8\n"
            "public.databasechangeloglock\t1\n"
            "users.users\t0\n"
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            custom_env, dump_dir = self._setup_mock_env(tmpdir, zero_user_counts)
            (dump_dir / "row-counts.txt").write_text(zero_user_counts)

            res = subprocess.run(
                [str(RESTORE_SCRIPT), str(dump_dir)],
                capture_output=True,
                text=True,
                env=custom_env,
            )
            self.assertEqual(res.returncode, 1)
            self.assertIn("Core table 'users.users' is missing or has 0 rows", res.stderr)

    def test_restore_locked_database_fails_closed(self):
        """When public.databasechangeloglock has locked=true, restore check fails closed."""
        valid_counts = (
            "notebooks.notebooks\t8\n"
            "public.databasechangelog\t8\n"
            "public.databasechangeloglock\t1\n"
            "users.users\t5\n"
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            custom_env, dump_dir = self._setup_mock_env(tmpdir, valid_counts, lock_status="t")
            (dump_dir / "row-counts.txt").write_text(valid_counts)

            res = subprocess.run(
                [str(RESTORE_SCRIPT), str(dump_dir)],
                capture_output=True,
                text=True,
                env=custom_env,
            )
            self.assertEqual(res.returncode, 1)
            self.assertIn("Liquibase lock check failed. Expected locked=false, got 't'", res.stderr)

    def test_restore_empty_database_fails_closed(self):
        """When restored database contains 0 tracked tables, script fails closed."""
        with tempfile.TemporaryDirectory() as tmpdir:
            custom_env, dump_dir = self._setup_mock_env(tmpdir, "")
            (dump_dir / "row-counts.txt").write_text("users.users\t5\n")

            res = subprocess.run(
                [str(RESTORE_SCRIPT), str(dump_dir)],
                capture_output=True,
                text=True,
                env=custom_env,
            )
            self.assertEqual(res.returncode, 1)
            self.assertIn("Restored database contains 0 tables in schemas", res.stderr)


def extract_production_row_count_query(schemas: list[str]) -> str:
    """Extract production row counting query from restore-disposable-db.sh parameterized with schemas."""
    content = RESTORE_SCRIPT.read_text(encoding="utf-8")
    start = content.find("SELECT string_agg(")
    if start == -1:
        raise ValueError(f"Start of row count query not found in {RESTORE_SCRIPT}")
    end = content.find(r"\gexec", start)
    if end == -1:
        raise ValueError(f"End of row count query not found in {RESTORE_SCRIPT}")
    raw_query = content[start : end + len(r"\gexec")]
    schema_list = ", ".join(f"'{s}'" for s in schemas)
    return re.sub(r"AND n\.nspname IN \([^)]+\)", f"AND n.nspname IN ({schema_list})", raw_query)


class TestSqlRowCountQuery(unittest.TestCase):
    """Validate dynamic SQL row counting query on live PostgreSQL if explicitly configured."""

    def test_backup_and_restore_row_count_queries_match(self):
        """Verify backup-aeza.sh and restore-disposable-db.sh contain identical row count SQL logic."""
        backup_content = BACKUP_SCRIPT.read_text(encoding="utf-8")
        restore_content = RESTORE_SCRIPT.read_text(encoding="utf-8")

        b_start = backup_content.find("SELECT string_agg(")
        b_end = backup_content.find(r"\gexec", b_start)
        self.assertNotEqual(b_start, -1, "Row count query start missing in backup-aeza.sh")
        self.assertNotEqual(b_end, -1, "Row count query end missing in backup-aeza.sh")
        raw_b = backup_content[b_start : b_end + len(r"\gexec")]

        r_start = restore_content.find("SELECT string_agg(")
        r_end = restore_content.find(r"\gexec", r_start)
        self.assertNotEqual(r_start, -1, "Row count query start missing in restore-disposable-db.sh")
        self.assertNotEqual(r_end, -1, "Row count query end missing in restore-disposable-db.sh")
        raw_r = restore_content[r_start : r_end + len(r"\gexec")]

        # backup-aeza.sh escapes quotes ('\'') and backslash (\\gexec) inside cat << SQL >&3
        b_clean = raw_b.replace(r"'\''", "'").replace(r"\\gexec", r"\gexec")
        self.assertEqual(b_clean.strip(), raw_r.strip())

    def _get_test_target(self):
        """
        Return (psql_path, target_db, is_disposable, base_db).
        Skips test if psql is absent, postgres unreachable, or no explicit test target is configured.
        Prevents auto-running destructive tests against ambient/default instances.
        """
        psql_path = shutil.which("psql")
        if not psql_path:
            self.skipTest("psql CLI not available in PATH")

        explicit_db = os.environ.get("TEST_POSTGRES_DB") or os.environ.get("PGDATABASE")
        explicit_host = os.environ.get("TEST_POSTGRES_HOST") or os.environ.get("PGHOST")
        explicit_opt_in = (
            os.environ.get("TEST_POSTGRES_ENABLED") in ("1", "true", "yes")
            or os.environ.get("JSNB_TEST_POSTGRES") in ("1", "true", "yes")
        )

        if not (explicit_db or explicit_host or explicit_opt_in):
            self.skipTest(
                "No explicit test PostgreSQL configuration (set TEST_POSTGRES_DB, PGHOST, or TEST_POSTGRES_ENABLED=1)"
            )

        base_db = explicit_db or "postgres"
        check = subprocess.run([psql_path, base_db, "-c", "SELECT 1;"], capture_output=True, text=True)
        if check.returncode != 0:
            check = subprocess.run([psql_path, "template1", "-c", "SELECT 1;"], capture_output=True, text=True)
            if check.returncode != 0:
                self.skipTest("Local PostgreSQL instance not reachable")
            base_db = "template1"

        if explicit_db and explicit_db not in ("postgres", "template1"):
            return psql_path, explicit_db, False, base_db

        disposable_db = f"jsnb_test_db_{uuid.uuid4().hex[:10]}"
        create_res = subprocess.run(
            [psql_path, base_db, "-c", f'CREATE DATABASE "{disposable_db}";'],
            capture_output=True,
            text=True,
        )
        if create_res.returncode == 0:
            return psql_path, disposable_db, True, base_db

        return psql_path, base_db, False, base_db

    def _cleanup_disposable_db(self, psql_path, base_db, disposable_db):
        term_sql = (
            f"SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
            f"WHERE datname = '{disposable_db}' AND pid <> pg_backend_pid();"
        )
        subprocess.run([psql_path, base_db, "-c", term_sql], capture_output=True)
        subprocess.run([psql_path, base_db, "-c", f'DROP DATABASE IF EXISTS "{disposable_db}";'], capture_output=True)

    def test_dynamic_sql_counts_actual_table_rows_not_catalog(self):
        psql_path, target_db, is_disposable, base_db = self._get_test_target()

        schema_u = f"test_u_{uuid.uuid4().hex[:12]}"
        schema_n = f"test_n_{uuid.uuid4().hex[:12]}"
        created_schemas = []

        try:
            # Create schemas strictly without IF NOT EXISTS
            subprocess.run([psql_path, target_db, "-c", f'CREATE SCHEMA "{schema_u}";'], check=True, capture_output=True)
            created_schemas.append(schema_u)
            subprocess.run([psql_path, target_db, "-c", f'CREATE SCHEMA "{schema_n}";'], check=True, capture_output=True)
            created_schemas.append(schema_n)

            setup_tables_sql = f"""
            CREATE TABLE "{schema_u}".users (id int, email text);
            INSERT INTO "{schema_u}".users VALUES (1, 'u1'), (2, 'u2'), (3, 'u3');
            CREATE TABLE "{schema_n}".notebooks (id int);
            """
            subprocess.run([psql_path, target_db, "-c", setup_tables_sql], check=True, capture_output=True)

            query = extract_production_row_count_query([schema_u, schema_n])

            # 1. Verify 3 rows on users and 0 rows on notebooks
            res1 = subprocess.run(
                [psql_path, target_db, "-X", "-A", "-t", "-F", "\t", "-v", "ON_ERROR_STOP=1"],
                input=query,
                capture_output=True,
                text=True,
                check=True,
            )
            self.assertIn(f"{schema_u}.users\t3", res1.stdout)
            self.assertIn(f"{schema_n}.notebooks\t0", res1.stdout)

            # 2. Truncate users table and verify count updates to 0 (NOT remaining 1 as in pg_class catalog bug)
            subprocess.run([psql_path, target_db, "-c", f'TRUNCATE "{schema_u}".users;'], check=True, capture_output=True)
            res2 = subprocess.run(
                [psql_path, target_db, "-X", "-A", "-t", "-F", "\t", "-v", "ON_ERROR_STOP=1"],
                input=query,
                capture_output=True,
                text=True,
                check=True,
            )
            self.assertIn(f"{schema_u}.users\t0", res2.stdout)
            self.assertNotIn(f"{schema_u}.users\t1", res2.stdout)
        finally:
            for s in created_schemas:
                subprocess.run([psql_path, target_db, "-c", f'DROP SCHEMA IF EXISTS "{s}" CASCADE;'], capture_output=True)
            if is_disposable:
                self._cleanup_disposable_db(psql_path, base_db, target_db)

    def test_preexisting_sentinel_schema_preserved(self):
        """Regression test: pre-existing schema and data must NOT be adopted or dropped."""
        psql_path, target_db, is_disposable, base_db = self._get_test_target()

        sentinel_schema = f"test_sentinel_{uuid.uuid4().hex[:12]}"
        subprocess.run([psql_path, target_db, "-c", f'CREATE SCHEMA "{sentinel_schema}";'], check=True, capture_output=True)
        try:
            subprocess.run(
                [psql_path, target_db, "-c", f'CREATE TABLE "{sentinel_schema}".reviewer_sentinel (id int, val text);'],
                check=True,
                capture_output=True,
            )
            subprocess.run(
                [psql_path, target_db, "-c", f'INSERT INTO "{sentinel_schema}".reviewer_sentinel VALUES (1, \'keep_me\');'],
                check=True,
                capture_output=True,
            )

            # Run test logic that uses isolated unique schemas
            test_schema = f"test_worker_{uuid.uuid4().hex[:12]}"
            created_schemas = []
            try:
                subprocess.run([psql_path, target_db, "-c", f'CREATE SCHEMA "{test_schema}";'], check=True, capture_output=True)
                created_schemas.append(test_schema)
                subprocess.run(
                    [psql_path, target_db, "-c", f'CREATE TABLE "{test_schema}".t (id int); INSERT INTO "{test_schema}".t VALUES (1);'],
                    check=True,
                    capture_output=True,
                )
                query = extract_production_row_count_query([test_schema])
                res = subprocess.run(
                    [psql_path, target_db, "-X", "-A", "-t", "-F", "\t", "-v", "ON_ERROR_STOP=1"],
                    input=query,
                    capture_output=True,
                    text=True,
                    check=True,
                )
                self.assertIn(f"{test_schema}.t\t1", res.stdout)
            finally:
                for s in created_schemas:
                    subprocess.run([psql_path, target_db, "-c", f'DROP SCHEMA IF EXISTS "{s}" CASCADE;'], capture_output=True)

            # Verify sentinel schema and data were completely preserved
            sentinel_check = subprocess.run(
                [psql_path, target_db, "-X", "-A", "-t", "-c", f"SELECT to_regnamespace('{sentinel_schema}') IS NOT NULL;"],
                capture_output=True,
                text=True,
                check=True,
            )
            self.assertEqual(sentinel_check.stdout.strip(), "t")

            data_check = subprocess.run(
                [psql_path, target_db, "-X", "-A", "-t", "-c", f'SELECT val FROM "{sentinel_schema}".reviewer_sentinel WHERE id = 1;'],
                capture_output=True,
                text=True,
                check=True,
            )
            self.assertEqual(data_check.stdout.strip(), "keep_me")
        finally:
            subprocess.run([psql_path, target_db, "-c", f'DROP SCHEMA IF EXISTS "{sentinel_schema}" CASCADE;'], capture_output=True)
            if is_disposable:
                self._cleanup_disposable_db(psql_path, base_db, target_db)

    def test_schema_creation_refuses_to_adopt_existing_schema(self):
        """Schema creation without IF NOT EXISTS fails closed if a name collision occurs."""
        psql_path, target_db, is_disposable, base_db = self._get_test_target()

        colliding_schema = f"test_existing_{uuid.uuid4().hex[:12]}"
        subprocess.run([psql_path, target_db, "-c", f'CREATE SCHEMA "{colliding_schema}";'], check=True, capture_output=True)
        try:
            attempt = subprocess.run(
                [psql_path, target_db, "-c", f'CREATE SCHEMA "{colliding_schema}";'],
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(attempt.returncode, 0)
            self.assertIn("already exists", attempt.stderr)
        finally:
            subprocess.run([psql_path, target_db, "-c", f'DROP SCHEMA IF EXISTS "{colliding_schema}" CASCADE;'], capture_output=True)
            if is_disposable:
                self._cleanup_disposable_db(psql_path, base_db, target_db)


if __name__ == "__main__":
    unittest.main()
