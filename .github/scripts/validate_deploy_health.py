#!/usr/bin/env python3
"""Validate a deployment health response read from standard input."""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any


class HealthError(ValueError):
    """Raised when a deployment health response is not acceptable."""


def validate_health(payload: Any, *, expected_environment: str) -> None:
    if not isinstance(payload, dict):
        raise HealthError("health response must be a JSON object")
    if payload.get("status") != "ok":
        raise HealthError("health status is not ok")
    if payload.get("environment") != expected_environment:
        raise HealthError(f"health environment is not {expected_environment}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--expected-environment", required=True)
    args = parser.parse_args()

    try:
        validate_health(
            json.load(sys.stdin),
            expected_environment=args.expected_environment,
        )
    except (HealthError, json.JSONDecodeError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
