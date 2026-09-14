from __future__ import annotations

import stat
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from validate_aeza_deploy_config import (  # noqa: E402
    ConfigError,
    validate_and_write_migration_env,
)


IMAGE_REGISTRY = "ghcr.io/larchanka-training"
IMAGE_TAG = "sha-9db0e65"


def valid_config(*, app_env: str = "staging") -> dict[str, object]:
    return {
        "services": {
            "api": {
                "image": f"{IMAGE_REGISTRY}/jsnotes-t2:api-{IMAGE_TAG}",
                "environment": {
                    "APP_NAME": "JS Notebook API",
                    "APP_ENV": app_env,
                    "DATABASE_URL": "postgresql://admin:secret@postgres:5432/wiki",
                    "JWT_SECRET": "jwt-secret-at-least-32-characters",
                    "OTP_HASH_SECRET": "otp-secret-at-least-32-characters",
                    "RESEND_API_KEY": "re_example",
                    "EMAIL_FROM": "login@jsnb.org",
                    "ALLOW_PLACEHOLDER_AUTH": "false",
                    "LLM_PROVIDER": "openrouter",
                    "LLM_OPENROUTER_API_KEY": "test key with $() ; shell symbols",
                    "LLM_ALLOWED_EMAILS": "developer@example.com",
                    "ENABLE_EXECUTE": "false",
                },
            },
            "frontend": {"image": f"{IMAGE_REGISTRY}/jsnotes-t2:ui-{IMAGE_TAG}"},
            "postgres": {
                "environment": {
                    "POSTGRES_USER": "admin",
                    "POSTGRES_PASSWORD": "password with $() ; shell symbols",
                    "POSTGRES_DB": "wiki",
                },
            },
        }
    }


class ValidateAezaDeployConfigTests(unittest.TestCase):
    def validate(
        self,
        config: dict[str, object],
        output: Path,
        *,
        expected_app_env: str = "staging",
        allowed_email_count: int | None = None,
        expected_database: str | None = None,
    ) -> None:
        validate_and_write_migration_env(
            config,
            image_registry=IMAGE_REGISTRY,
            image_tag=IMAGE_TAG,
            expected_app_env=expected_app_env,
            allowed_email_count=allowed_email_count,
            expected_database=expected_database,
            migration_env_file=output,
        )

    def test_treats_spaces_and_shell_symbols_as_data(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "migration.env"
            self.validate(valid_config(), output)

            self.assertEqual(stat.S_IMODE(output.stat().st_mode), 0o600)
            self.assertIn(
                "LIQUIBASE_COMMAND_PASSWORD=password with $() ; shell symbols\n",
                output.read_text(encoding="utf-8"),
            )

    def test_accepts_production_with_exactly_two_allowlisted_accounts(self) -> None:
        config = valid_config(app_env="production")
        config["services"]["api"]["environment"]["LLM_ALLOWED_EMAILS"] = (  # type: ignore[index]
            "developer@example.com,owner@example.com"
        )
        with tempfile.TemporaryDirectory() as directory:
            self.validate(
                config,
                Path(directory) / "migration.env",
                expected_app_env="production",
                allowed_email_count=2,
            )

    def test_rejects_wrong_environment_guard(self) -> None:
        config = valid_config(app_env="production")
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ConfigError, "APP_ENV"):
                self.validate(config, Path(directory) / "migration.env")

    def test_rejects_placeholder_auth_mode(self) -> None:
        config = valid_config()
        config["services"]["api"]["environment"]["ALLOW_PLACEHOLDER_AUTH"] = (  # type: ignore[index]
            "true"
        )
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ConfigError, "ALLOW_PLACEHOLDER_AUTH"):
                self.validate(config, Path(directory) / "migration.env")

    def test_rejects_placeholder_secret(self) -> None:
        config = valid_config()
        config["services"]["api"]["environment"]["JWT_SECRET"] = "change-me"  # type: ignore[index]
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ConfigError, "JWT_SECRET"):
                self.validate(config, Path(directory) / "migration.env")

    def test_rejects_missing_required_runtime_value(self) -> None:
        config = valid_config()
        config["services"]["api"]["environment"]["LLM_ALLOWED_EMAILS"] = ""  # type: ignore[index]
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ConfigError, "LLM_ALLOWED_EMAILS"):
                self.validate(config, Path(directory) / "migration.env")

    def test_rejects_wrong_allowlist_count(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ConfigError, "exactly 2"):
                self.validate(
                    valid_config(app_env="production"),
                    Path(directory) / "migration.env",
                    expected_app_env="production",
                    allowed_email_count=2,
                )

    def test_rejects_duplicate_allowlist_entries(self) -> None:
        config = valid_config()
        config["services"]["api"]["environment"]["LLM_ALLOWED_EMAILS"] = (  # type: ignore[index]
            "developer@example.com,Developer@example.com"
        )
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ConfigError, "unique"):
                self.validate(config, Path(directory) / "migration.env")

    def test_rejects_rehearsal_database_target(self) -> None:
        config = valid_config()
        config["services"]["postgres"]["environment"]["POSTGRES_DB"] = (  # type: ignore[index]
            "wiki_rehearsal"
        )
        config["services"]["api"]["environment"]["DATABASE_URL"] = (  # type: ignore[index]
            "postgresql://admin:secret@postgres:5432/wiki_rehearsal"
        )
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ConfigError, "POSTGRES_DB"):
                self.validate(
                    config,
                    Path(directory) / "migration.env",
                    expected_database="wiki",
                )

    def test_rejects_image_from_unexpected_tag(self) -> None:
        config = valid_config()
        config["services"]["api"]["image"] = (  # type: ignore[index]
            f"{IMAGE_REGISTRY}/jsnotes-t2:api-latest"
        )
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ConfigError, "api"):
                self.validate(config, Path(directory) / "migration.env")

    def test_rejects_newline_in_migration_value(self) -> None:
        config = valid_config()
        config["services"]["postgres"]["environment"]["POSTGRES_PASSWORD"] = (  # type: ignore[index]
            "line1\nline2"
        )
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ConfigError, "control characters"):
                self.validate(config, Path(directory) / "migration.env")


if __name__ == "__main__":
    unittest.main()
