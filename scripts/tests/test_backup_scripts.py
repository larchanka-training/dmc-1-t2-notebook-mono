#!/usr/bin/env python3
"""
Unit and functional tests for Aeza backup and restore verification scripts:
- scripts/backup-aeza.sh
- scripts/restore-disposable-db.sh
"""

import hashlib
import os
import shutil
import stat
import subprocess
import tempfile
import unittest
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


class TestSqlRowCountQuery(unittest.TestCase):
    """Validate dynamic SQL row counting query on live PostgreSQL if available."""

    def test_dynamic_sql_counts_actual_table_rows_not_catalog(self):
        psql_path = shutil.which("psql")
        if not psql_path:
            self.skipTest("psql CLI not available in PATH")

        check = subprocess.run([psql_path, "postgres", "-c", "SELECT 1;"], capture_output=True, text=True)
        if check.returncode != 0:
            self.skipTest("Local PostgreSQL instance not reachable")

        schema_u = "test_pr237_users"
        schema_n = "test_pr237_notebooks"

        setup_sql = f"""
        CREATE SCHEMA IF NOT EXISTS {schema_u};
        CREATE SCHEMA IF NOT EXISTS {schema_n};
        CREATE TABLE IF NOT EXISTS {schema_u}.users (id int, email text);
        INSERT INTO {schema_u}.users VALUES (1, 'u1'), (2, 'u2'), (3, 'u3');
        CREATE TABLE IF NOT EXISTS {schema_n}.notebooks (id int);
        """
        subprocess.run([psql_path, "postgres", "-c", setup_sql], check=True, capture_output=True)

        query = f"""
        SELECT string_agg(
          format('SELECT %L AS table_name, count(*)::bigint AS rows FROM %I.%I',
                 n.nspname || '.' || c.relname, n.nspname, c.relname),
          ' UNION ALL '
        ) || ' ORDER BY 1;'
        FROM pg_class c
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE c.relkind = 'r'
          AND n.nspname IN ('{schema_u}', '{schema_n}')
        \\gexec
        """

        try:
            # 1. Verify 3 rows on users and 0 rows on notebooks
            res1 = subprocess.run(
                [psql_path, "postgres", "-X", "-A", "-t", "-F", "\t", "-v", "ON_ERROR_STOP=1"],
                input=query,
                capture_output=True,
                text=True,
                check=True,
            )
            self.assertIn(f"{schema_u}.users\t3", res1.stdout)
            self.assertIn(f"{schema_n}.notebooks\t0", res1.stdout)

            # 2. Truncate users table and verify count updates to 0 (NOT remaining 1 as in pg_class bug)
            subprocess.run([psql_path, "postgres", "-c", f"TRUNCATE {schema_u}.users;"], check=True, capture_output=True)
            res2 = subprocess.run(
                [psql_path, "postgres", "-X", "-A", "-t", "-F", "\t", "-v", "ON_ERROR_STOP=1"],
                input=query,
                capture_output=True,
                text=True,
                check=True,
            )
            self.assertIn(f"{schema_u}.users\t0", res2.stdout)
            self.assertNotIn(f"{schema_u}.users\t1", res2.stdout)
        finally:
            cleanup_sql = f"DROP SCHEMA IF EXISTS {schema_u} CASCADE; DROP SCHEMA IF EXISTS {schema_n} CASCADE;"
            subprocess.run([psql_path, "postgres", "-c", cleanup_sql], capture_output=True)


if __name__ == "__main__":
    unittest.main()
