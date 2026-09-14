#!/usr/bin/env python3
"""Validate deployment UI root response (HTTP 200, COOP/COEP headers, and root markup)."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


class UIValidationError(ValueError):
    """Raised when a UI deployment response is not acceptable."""


def parse_headers(raw_headers: str) -> tuple[int, dict[str, str]]:
    """Parse HTTP headers string into (status_code, headers_dict).

    If multiple HTTP header blocks are present (e.g. after redirects or 100-continue),
    the final block is parsed.
    """
    blocks = [
        block.strip()
        for block in re.split(r"(?:\r?\n){2,}", raw_headers.strip())
        if block.strip()
    ]
    if not blocks:
        raise UIValidationError("no HTTP header block found")

    final_block = blocks[-1]
    lines = final_block.splitlines()
    if not lines:
        raise UIValidationError("empty HTTP header block")

    status_line = lines[0].strip()
    match = re.match(r"^HTTP/\d+(?:\.\d+)?\s+(\d{3})", status_line)
    if not match:
        raise UIValidationError(f"invalid HTTP status line: {status_line!r}")
    status_code = int(match.group(1))

    headers: dict[str, str] = {}
    for line in lines[1:]:
        if ":" in line:
            name, value = line.split(":", 1)
            headers[name.strip().casefold()] = value.strip()

    return status_code, headers


def validate_ui_response(raw_headers: str, body: str) -> None:
    status_code, headers = parse_headers(raw_headers)
    if status_code != 200:
        raise UIValidationError(f"expected HTTP 200, got HTTP {status_code}")

    coop = headers.get("cross-origin-opener-policy")
    if not coop:
        raise UIValidationError("missing Cross-Origin-Opener-Policy header")
    if coop.casefold() != "same-origin":
        raise UIValidationError(
            f"expected Cross-Origin-Opener-Policy 'same-origin', got {coop!r}"
        )

    coep = headers.get("cross-origin-embedder-policy")
    if not coep:
        raise UIValidationError("missing Cross-Origin-Embedder-Policy header")
    if coep.casefold() != "require-corp":
        raise UIValidationError(
            f"expected Cross-Origin-Embedder-Policy 'require-corp', got {coep!r}"
        )

    if '<div id="root">' not in body and '<div id="root"' not in body:
        raise UIValidationError("response body does not contain '<div id=\"root\">'")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate deployment UI root response (headers and body)"
    )
    parser.add_argument(
        "--headers-file",
        type=Path,
        help="Path to file containing raw HTTP response headers",
    )
    parser.add_argument(
        "--body-file",
        type=Path,
        help="Path to file containing response body HTML",
    )
    args = parser.parse_args()

    try:
        if args.headers_file is not None or args.body_file is not None:
            if args.headers_file is None or args.body_file is None:
                raise UIValidationError(
                    "both --headers-file and --body-file must be specified together"
                )
            raw_headers = args.headers_file.read_text(encoding="utf-8", errors="replace")
            body = args.body_file.read_text(encoding="utf-8", errors="replace")
        else:
            # Read combined HTTP response from stdin (e.g. curl -i output)
            content = sys.stdin.read()
            parts = re.split(r"(?:\r?\n){2}", content, maxsplit=1)
            if len(parts) < 2:
                raise UIValidationError(
                    "input from stdin must contain headers and body separated by an empty line"
                )
            raw_headers, body = parts[0], parts[1]

        validate_ui_response(raw_headers, body)
    except (UIValidationError, OSError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1

    print("Deployment UI response: OK (HTTP 200, COOP=same-origin, COEP=require-corp, root mount present)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
