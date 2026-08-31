#!/usr/bin/env python3
"""Validate rendered Aeza staging Compose config without executing env input."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any


class ConfigError(ValueError):
    """Raised when the rendered staging configuration is unsafe or incomplete."""


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
    "APP_ENV": "staging",
    "LLM_PROVIDER": "openrouter",
    "ENABLE_EXECUTE": "false",
}

REQUIRED_POSTGRES_VALUES = (
    "POSTGRES_USER",
    "POSTGRES_PASSWORD",
    "POSTGRES_DB",
)


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
            "jdbc:postgresql://postgres:5432/"
            + postgres_environment["POSTGRES_DB"]
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

    descriptor = os.open(
        path,
        os.O_WRONLY | os.O_CREAT | os.O_TRUNC,
        0o600,
    )
    os.fchmod(descriptor, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as output:
        for name, value in values.items():
            output.write(f"{name}={value}\n")


def validate_and_write_migration_env(
    config: dict[str, Any],
    *,
    image_registry: str,
    image_tag: str,
    migration_env_file: Path,
) -> None:
    api_environment = _service_environment(config, "api")
    postgres_environment = _service_environment(config, "postgres")

    _require_non_empty(api_environment, REQUIRED_API_VALUES)
    _require_non_empty(postgres_environment, REQUIRED_POSTGRES_VALUES)

    invalid_guards = [
        name
        for name, expected_value in EXPECTED_API_VALUES.items()
        if api_environment.get(name) != expected_value
    ]
    if invalid_guards:
        raise ConfigError(
            "staging runtime guards failed: " + ", ".join(invalid_guards)
        )

    _validate_images(config, image_registry, image_tag)
    _write_migration_env(migration_env_file, postgres_environment)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--image-registry", required=True)
    parser.add_argument("--image-tag", required=True)
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
            migration_env_file=args.migration_env_file,
        )
    except (ConfigError, json.JSONDecodeError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1

    print("Staging Compose configuration: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
