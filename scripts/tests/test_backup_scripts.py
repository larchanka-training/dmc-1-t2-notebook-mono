#!/usr/bin/env python3
"""
Unit and functional tests for Aeza backup and restore verification scripts:
- scripts/backup-aeza.sh
- scripts/restore-disposable-db.sh
"""

import hashlib
import os
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
            # Unless the test machine actually has hostname fortunate-pink
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


class TestRestoreDisposableDbCli(unittest.TestCase):
    """Test CLI behavior and validation for restore-disposable-db.sh."""

    def test_help_flag(self):
        res = subprocess.run([str(RESTORE_SCRIPT), "--help"], capture_output=True, text=True)
        self.assertEqual(res.returncode, 0)
        self.assertIn("Usage:", res.stdout)
        self.assertIn("--keep-on-failure", res.stdout)
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

    def test_dry_run_with_valid_checksum(self):
        """Test that dry-run passes when checksum matches and dump is non-empty."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            dump_file = tmp_path / "database.dump"
            content = b"PGDMP\x01\x0f\x00\x00\x00sample_mock_dump_data"
            dump_file.write_bytes(content)

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

    def test_checksum_mismatch_fails(self):
        """Test that checksum mismatch fails execution."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            dump_file = tmp_path / "database.dump"
            dump_file.write_bytes(b"corrupted content")

            sums_file = tmp_path / "SHA256SUMS"
            sums_file.write_text("0000000000000000000000000000000000000000000000000000000000000000  database.dump\n")

            res = subprocess.run(
                [str(RESTORE_SCRIPT), "--dry-run", str(tmp_path)],
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(res.returncode, 0)


if __name__ == "__main__":
    unittest.main()
