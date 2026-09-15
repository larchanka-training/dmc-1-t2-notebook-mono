#!/usr/bin/env python3
"""
Unit and functional tests for Aeza backup and restore verification scripts:
- scripts/backup-aeza.sh
- scripts/restore-disposable-db.sh
"""

import hashlib
import os
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

            # Environment with empty or minimal PATH containing no age/gpg
            custom_env = os.environ.copy()
            custom_env["PATH"] = "/usr/bin:/bin"  # standard system bins, typically no age

            # Test only if age and gpg are not in /usr/bin or /bin
            has_age_or_gpg = Path("/usr/bin/age").exists() or Path("/bin/age").exists() or \
                             Path("/usr/bin/gpg").exists() or Path("/bin/gpg").exists()
            if not has_age_or_gpg:
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


if __name__ == "__main__":
    unittest.main()
