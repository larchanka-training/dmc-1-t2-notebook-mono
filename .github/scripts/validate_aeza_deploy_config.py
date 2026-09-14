#!/usr/bin/env python3
"""Validate rendered Aeza Compose config without executing env-file input."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlsplit


class ConfigError(ValueError):
    """Raised when a rendered deployment configuration is unsafe or incomplete."""


REQUIRED_API_VALUES = (
    "DATABASE_URL",
    "JWT_SECRET",
    "OTP_HASH_SECRET",
    "RESEND_API_KEY",
    "EMAIL_FROM",
    "LLM_OPENROUTER_API_KEY",
    "LLM_ALLOWED_EMAILS",
)

EXPECTED_API_VALUES = {
    "LLM_PROVIDER": "openrouter",
    "ENABLE_EXECUTE": "false",
    "ALLOW_PLACEHOLDER_AUTH": "false",
}

REQUIRED_POSTGRES_VALUES = (
    "POSTGRES_USER",
    "POSTGRES_PASSWORD",
    "POSTGRES_DB",
)

PLACEHOLDER_VALUES = {
    "",
    "change-me",
    "change-me-at-least-32-characters",
    "re_xxx",
    "login@example.com",
}


def _service_environment(config: dict[str, Any], service_name: str) -> dict[str, str]:
    services = config.get("services")
    if not isinstance(services, dict):
        raise ConfigError("rendered Compose config has no services mapping")

    service = services.get(service_name)
    if not isinstance(service, dict):
        raise ConfigError(f"rendered Compose config has no {service_name} service")

    environment = service.get("environment")
    if not isinstance(environment, dict):
        raise ConfigError(f"rendered {service_name} service has no environment mapping")

    return {
        str(key): "" if value is None else str(value)
        for key, value in environment.items()
    }


def _require_non_empty(environment: dict[str, str], names: tuple[str, ...]) -> None:
    missing = [name for name in names if not environment.get(name)]
    if missing:
        raise ConfigError(f"required runtime values are empty: {', '.join(missing)}")


def _reject_placeholders(environment: dict[str, str], names: tuple[str, ...]) -> None:
    placeholders = [
        name
        for name in names
        if environment.get(name, "").strip() in PLACEHOLDER_VALUES
    ]
    if placeholders:
        raise ConfigError(
            "required runtime values still use placeholders: " + ", ".join(placeholders)
        )


def _validate_database_target(
    api_environment: dict[str, str],
    postgres_environment: dict[str, str],
    expected_database: str | None,
) -> None:
    database_url = urlsplit(api_environment["DATABASE_URL"])
    configured_database = postgres_environment["POSTGRES_DB"]
    expected_user = postgres_environment["POSTGRES_USER"]

    try:
        port = database_url.port
    except ValueError as error:
        raise ConfigError("DATABASE_URL has an invalid port") from error

    invalid = (
        database_url.scheme != "postgresql"
        or database_url.hostname != "postgres"
        or (port or 5432) != 5432
        or unquote(database_url.username or "") != expected_user
        or database_url.path != f"/{configured_database}"
        or database_url.query
        or database_url.fragment
    )
    if invalid:
        raise ConfigError(
            "DATABASE_URL must target the Compose postgres service and POSTGRES_DB"
        )
    if expected_database is not None and configured_database != expected_database:
        raise ConfigError(f"POSTGRES_DB must be {expected_database}")


def _validate_allowlist(
    api_environment: dict[str, str], expected_count: int | None
) -> None:
    emails = [
        email.strip()
        for email in api_environment["LLM_ALLOWED_EMAILS"].split(",")
        if email.strip()
    ]
    if not emails or len(emails) != len(set(email.casefold() for email in emails)):
        raise ConfigError("LLM_ALLOWED_EMAILS must contain unique non-empty emails")
    if any(
        email.count("@") != 1 or any(character.isspace() for character in email)
        for email in emails
    ):
        raise ConfigError("LLM_ALLOWED_EMAILS contains an invalid email entry")
    if expected_count is not None and len(emails) != expected_count:
        raise ConfigError(
            f"LLM_ALLOWED_EMAILS must contain exactly {expected_count} accounts"
        )


def _validate_images(
    config: dict[str, Any], image_registry: str, image_tag: str
) -> None:
    services = config.get("services")
    if not isinstance(services, dict):
        raise ConfigError("rendered Compose config has no services mapping")

    expected_images = {
        "api": f"{image_registry}/jsnotes-t2:api-{image_tag}",
        "frontend": f"{image_registry}/jsnotes-t2:ui-{image_tag}",
    }
    mismatched = [
        service_name
        for service_name, expected_image in expected_images.items()
        if not isinstance(services.get(service_name), dict)
        or services[service_name].get("image") != expected_image
    ]
    if mismatched:
        raise ConfigError(
            "rendered image does not use the requested registry/tag for: "
            + ", ".join(mismatched)
        )


def _write_migration_env(path: Path, postgres_environment: dict[str, str]) -> None:
    values = {
        "LIQUIBASE_COMMAND_URL": (
            "jdbc:postgresql://postgres:5432/" + postgres_environment["POSTGRES_DB"]
        ),
        "LIQUIBASE_COMMAND_USERNAME": postgres_environment["POSTGRES_USER"],
        "LIQUIBASE_COMMAND_PASSWORD": postgres_environment["POSTGRES_PASSWORD"],
        "LIQUIBASE_COMMAND_CONTEXTS": "production",
        "LIQUIBASE_COMMAND_CHANGELOG_FILE": "changelog-master.xml",
    }
    invalid = [
        name
        for name, value in values.items()
        if any(character in value for character in ("\0", "\r", "\n"))
    ]
    if invalid:
        raise ConfigError(
            "migration environment values contain unsupported control characters: "
            + ", ".join(invalid)
        )

    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    os.fchmod(descriptor, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as output:
        for name, value in values.items():
            output.write(f"{name}={value}\n")


def validate_and_write_migration_env(
    config: dict[str, Any],
    *,
    image_registry: str,
    image_tag: str,
    expected_app_env: str,
    migration_env_file: Path,
    allowed_email_count: int | None = None,
    expected_database: str | None = None,
) -> None:
    api_environment = _service_environment(config, "api")
    postgres_environment = _service_environment(config, "postgres")

    _require_non_empty(api_environment, REQUIRED_API_VALUES)
    _require_non_empty(postgres_environment, REQUIRED_POSTGRES_VALUES)
    _reject_placeholders(
        api_environment,
        (
            "JWT_SECRET",
            "OTP_HASH_SECRET",
            "RESEND_API_KEY",
            "EMAIL_FROM",
            "LLM_OPENROUTER_API_KEY",
        ),
    )
    _reject_placeholders(postgres_environment, REQUIRED_POSTGRES_VALUES)

    expected_api_values = {**EXPECTED_API_VALUES, "APP_ENV": expected_app_env}
    invalid_guards = [
        name
        for name, expected_value in expected_api_values.items()
        if api_environment.get(name) != expected_value
    ]
    if invalid_guards:
        raise ConfigError("runtime guards failed: " + ", ".join(invalid_guards))

    _validate_database_target(api_environment, postgres_environment, expected_database)
    _validate_allowlist(api_environment, allowed_email_count)
    _validate_images(config, image_registry, image_tag)
    _write_migration_env(migration_env_file, postgres_environment)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--image-registry", required=True)
    parser.add_argument("--image-tag", required=True)
    parser.add_argument(
        "--expected-app-env", choices=("staging", "production"), required=True
    )
    parser.add_argument("--allowed-email-count", type=int)
    parser.add_argument("--expected-database")
    parser.add_argument("--migration-env-file", required=True, type=Path)
    args = parser.parse_args()

    try:
        config = json.load(sys.stdin)
        if not isinstance(config, dict):
            raise ConfigError("rendered Compose config is not a JSON object")
        validate_and_write_migration_env(
            config,
            image_registry=args.image_registry,
            image_tag=args.image_tag,
            expected_app_env=args.expected_app_env,
            allowed_email_count=args.allowed_email_count,
            expected_database=args.expected_database,
            migration_env_file=args.migration_env_file,
        )
    except (ConfigError, json.JSONDecodeError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1

    print(f"{args.expected_app_env.capitalize()} Compose configuration: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
