#!/usr/bin/env python3
"""Validate an API readiness health response read from standard input or arguments."""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any


class ReadinessError(ValueError):
    """Raised when an API readiness health response does not satisfy acceptance criteria."""


def validate_readiness(payload: Any) -> None:
    """Validate that the readiness payload has status: 'ok' and database component status: 'ok'."""
    if not isinstance(payload, dict):
        raise ReadinessError("Readiness response must be a JSON object")

    status = payload.get("status")
    if status != "ok":
        raise ReadinessError(f"Readiness top-level status is '{status}', expected 'ok'")

    components = payload.get("components")
    if not isinstance(components, list):
        raise ReadinessError("Readiness 'components' field must be a list")

    database_status: str | None = None
    for comp in components:
        if isinstance(comp, dict) and comp.get("name") == "database":
            database_status = comp.get("status")
            break

    if database_status is None:
        raise ReadinessError("Readiness response is missing the 'database' component")

    if database_status != "ok":
        raise ReadinessError(
            f"Readiness database component status is '{database_status}', expected 'ok'"
        )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate /api/v1/health/ready response JSON against strict gate criteria."
    )
    parser.add_argument(
        "payload",
        nargs="?",
        default=None,
        help="JSON payload string. If omitted, payload is read from standard input.",
    )
    args = parser.parse_args()

    try:
        if args.payload is not None:
            data = json.loads(args.payload)
        else:
            data = json.load(sys.stdin)
        validate_readiness(data)
    except (ReadinessError, json.JSONDecodeError) as error:
        print(f"GATE BARRIER ERROR: {error}", file=sys.stderr)
        return 1

    print("GATE BARRIER OK: API and PostgreSQL readiness check passed successfully.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
