#!/usr/bin/env python3
"""Validate deployment UI root response (HTTP 200, COOP/COEP headers, and root markup)."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


class UIValidationError(ValueError):
    """Raised when a UI deployment response is not acceptable."""


def extract_final_header_block(raw_headers: str) -> str:
    """Extract the final HTTP header block from raw_headers string.

    Handles intermediate header blocks from redirects or 100-continue.
    """
    blocks = [
        block.strip()
        for block in re.split(r"(?:\r?\n){2,}", raw_headers.strip())
        if block.strip()
    ]
    if not blocks:
        raise UIValidationError("no HTTP header block found")
    return blocks[-1]


def parse_headers(raw_headers: str) -> tuple[int, dict[str, list[str]]]:
    """Parse HTTP headers string into (status_code, headers_multidict).

    If multiple HTTP header blocks are present (e.g. after redirects or 100-continue),
    the final block is parsed. Header names are lowercased. Multiple occurrences of
    the same header name are preserved in list values to allow duplicate detection.
    """
    final_block = extract_final_header_block(raw_headers)
    lines = final_block.splitlines()
    if not lines:
        raise UIValidationError("empty HTTP header block")

    status_line = lines[0].strip()
    match = re.match(r"^HTTP/\d+(?:\.\d+)?\s+(\d{3})", status_line)
    if not match:
        raise UIValidationError(f"invalid HTTP status line: {status_line!r}")
    status_code = int(match.group(1))

    headers: dict[str, list[str]] = {}
    for line in lines[1:]:
        if ":" in line:
            name, value = line.split(":", 1)
            key = name.strip().casefold()
            headers.setdefault(key, []).append(value.strip())

    return status_code, headers


def validate_ui_response(raw_headers: str, body: str) -> None:
    status_code, headers = parse_headers(raw_headers)
    if status_code != 200:
        raise UIValidationError(f"expected HTTP 200, got HTTP {status_code}")

    coop_values = headers.get("cross-origin-opener-policy", [])
    if not coop_values:
        raise UIValidationError("missing Cross-Origin-Opener-Policy header")
    if len(coop_values) > 1:
        raise UIValidationError("duplicate Cross-Origin-Opener-Policy header")
    coop = coop_values[0]
    if coop != "same-origin":
        raise UIValidationError(
            f"expected Cross-Origin-Opener-Policy 'same-origin', got {coop!r}"
        )

    coep_values = headers.get("cross-origin-embedder-policy", [])
    if not coep_values:
        raise UIValidationError("missing Cross-Origin-Embedder-Policy header")
    if len(coep_values) > 1:
        raise UIValidationError("duplicate Cross-Origin-Embedder-Policy header")
    coep = coep_values[0]
    if coep != "require-corp":
        raise UIValidationError(
            f"expected Cross-Origin-Embedder-Policy 'require-corp', got {coep!r}"
        )

    content_type_values = headers.get("content-type", [])
    if not content_type_values:
        raise UIValidationError("missing Content-Type header")
    content_type = content_type_values[0]
    media_type = content_type.split(";")[0].strip().casefold()
    if media_type != "text/html":
        raise UIValidationError(
            f"expected Content-Type text/html, got {content_type!r}"
        )

    if '<div id="root">' not in body and '<div id="root"' not in body:
        raise UIValidationError("response body does not contain '<div id=\"root\">'")


def split_http_response_stream(content: str) -> tuple[str, str]:
    """Split an HTTP response stream (e.g. from stdin / curl -i) into (headers, body).

    Frames consecutive HTTP responses (e.g. 1xx informational, CONNECT 200,
    or 3xx redirects) and extracts the final response headers and the body.
    Only intermediate status codes (1xx, 3xx, or 200 Connection established)
    can be followed by another HTTP response.
    """
    remaining = content.lstrip("\r\n")
    header_blocks: list[str] = []
    body = ""

    while remaining:
        if not re.match(r"^HTTP/\d+(?:\.\d+)?\s+\d{3}", remaining):
            break

        parts = re.split(r"\r?\n\r?\n", remaining, maxsplit=1)
        if len(parts) < 2:
            break

        header_block, after = parts[0], parts[1]
        header_blocks.append(header_block)

        status_line = header_block.splitlines()[0].strip()
        match = re.match(r"^HTTP/\d+(?:\.\d+)?\s+(\d{3})(?:\s+(.*))?", status_line)
        if not match:
            break
        status_code = int(match.group(1))
        reason_phrase = (match.group(2) or "").strip().lower()

        is_intermediate = (
            100 <= status_code < 200
            or 300 <= status_code < 400
            or (status_code == 200 and "connection established" in reason_phrase)
        )

        # Only intermediate responses can advance to another HTTP response block
        if is_intermediate and re.match(r"^HTTP/\d+(?:\.\d+)?\s+\d{3}", after):
            remaining = after
            continue

        body = after
        break

    if not header_blocks:
        raise UIValidationError(
            "input must start with an HTTP status line followed by headers and body separated by an empty line"
        )

    return header_blocks[-1], body


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
            raw_headers = args.headers_file.read_text(
                encoding="utf-8", errors="replace"
            )
            body = args.body_file.read_text(encoding="utf-8", errors="replace")
        else:
            # Read combined HTTP response from stdin (e.g. curl -i output)
            content = sys.stdin.read()
            raw_headers, body = split_http_response_stream(content)

        validate_ui_response(raw_headers, body)
    except (UIValidationError, OSError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1

    print(
        "Deployment UI response: OK (HTTP 200, Content-Type=text/html, COOP=same-origin, COEP=require-corp, root mount present)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
