from __future__ import annotations

import stat
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from validate_aeza_staging_config import (  # noqa: E402
    ConfigError,
    validate_and_write_migration_env,
)


IMAGE_REGISTRY = "ghcr.io/larchanka-training"
IMAGE_TAG = "sha-9db0e65"


def valid_config() -> dict[str, object]:
    return {
        "services": {
            "api": {
                "image": f"{IMAGE_REGISTRY}/jsnotes-t2:api-{IMAGE_TAG}",
                "environment": {
                    "APP_NAME": "JS Notebook API",
                    "APP_ENV": "staging",
                    "DATABASE_URL": "postgresql://admin:secret@postgres:5432/wiki",
                    "JWT_SECRET": "jwt-secret-at-least-32-characters",
                    "OTP_HASH_SECRET": "otp-secret-at-least-32-characters",
                    "RESEND_API_KEY": "re_example",
                    "EMAIL_FROM": "login@example.com",
                    "LLM_PROVIDER": "openrouter",
                    "LLM_OPENROUTER_API_KEY": "sk-or-v1-value with $() ; symbols",
                    "LLM_ALLOWED_EMAILS": "developer@example.com",
                    "ENABLE_EXECUTE": "false",
                },
            },
            "frontend": {
                "image": f"{IMAGE_REGISTRY}/jsnotes-t2:ui-{IMAGE_TAG}",
            },
            "postgres": {
                "environment": {
                    "POSTGRES_USER": "admin user",
                    "POSTGRES_PASSWORD": "password with $() ; shell symbols",
                    "POSTGRES_DB": "wiki",
                },
            },
        }
    }


class ValidateAezaStagingConfigTests(unittest.TestCase):
    def test_treats_spaces_and_shell_symbols_as_data(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "migration.env"

            validate_and_write_migration_env(
                valid_config(),
                image_registry=IMAGE_REGISTRY,
                image_tag=IMAGE_TAG,
                migration_env_file=output,
            )

            self.assertEqual(stat.S_IMODE(output.stat().st_mode), 0o600)
            self.assertIn(
                "LIQUIBASE_COMMAND_USERNAME=admin user\n",
                output.read_text(encoding="utf-8"),
            )
            self.assertIn(
                "LIQUIBASE_COMMAND_PASSWORD=password with $() ; shell symbols\n",
                output.read_text(encoding="utf-8"),
            )

    def test_rejects_wrong_staging_guard(self) -> None:
        config = valid_config()
        config["services"]["api"]["environment"]["APP_ENV"] = "production"  # type: ignore[index]

        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ConfigError, "APP_ENV"):
                validate_and_write_migration_env(
                    config,
                    image_registry=IMAGE_REGISTRY,
                    image_tag=IMAGE_TAG,
                    migration_env_file=Path(directory) / "migration.env",
                )

    def test_rejects_missing_required_runtime_value(self) -> None:
        config = valid_config()
        config["services"]["api"]["environment"]["LLM_ALLOWED_EMAILS"] = ""  # type: ignore[index]

        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ConfigError, "LLM_ALLOWED_EMAILS"):
                validate_and_write_migration_env(
                    config,
                    image_registry=IMAGE_REGISTRY,
                    image_tag=IMAGE_TAG,
                    migration_env_file=Path(directory) / "migration.env",
                )

    def test_rejects_image_from_unexpected_tag(self) -> None:
        config = valid_config()
        config["services"]["api"]["image"] = (  # type: ignore[index]
            f"{IMAGE_REGISTRY}/jsnotes-t2:api-latest"
        )

        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ConfigError, "api"):
                validate_and_write_migration_env(
                    config,
                    image_registry=IMAGE_REGISTRY,
                    image_tag=IMAGE_TAG,
                    migration_env_file=Path(directory) / "migration.env",
                )

    def test_rejects_newline_in_migration_value(self) -> None:
        config = valid_config()
        config["services"]["postgres"]["environment"][  # type: ignore[index]
            "POSTGRES_PASSWORD"
        ] = "line1\nline2"

        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ConfigError, "control characters"):
                validate_and_write_migration_env(
                    config,
                    image_registry=IMAGE_REGISTRY,
                    image_tag=IMAGE_TAG,
                    migration_env_file=Path(directory) / "migration.env",
                )


if __name__ == "__main__":
    unittest.main()
