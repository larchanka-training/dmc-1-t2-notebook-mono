from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from validate_deploy_ui import UIValidationError, parse_headers, validate_ui_response  # noqa: E402


VALID_HTTP11_HEADERS = """HTTP/1.1 200 OK\r
Date: Mon, 14 Sep 2026 20:00:00 GMT\r
Content-Type: text/html; charset=utf-8\r
Cross-Origin-Opener-Policy: same-origin\r
Cross-Origin-Embedder-Policy: require-corp\r
Connection: keep-alive\r
\r
"""

VALID_HTTP2_HEADERS = """HTTP/2 200\r
date: Mon, 14 Sep 2026 20:00:00 GMT\r
content-type: text/html\r
cross-origin-opener-policy: same-origin\r
cross-origin-embedder-policy: require-corp\r
server: cloudflare\r
\r
"""

VALID_BODY = """<!doctype html>
<html lang="en">
  <head><title>JS Notebook</title></head>
  <body><div id="root"></div></body>
</html>
"""


class ValidateDeployUITests(unittest.TestCase):
    def test_accepts_valid_http11_response(self) -> None:
        validate_ui_response(VALID_HTTP11_HEADERS, VALID_BODY)

    def test_accepts_valid_http2_response(self) -> None:
        validate_ui_response(VALID_HTTP2_HEADERS, VALID_BODY)

    def test_accepts_response_after_redirect_blocks(self) -> None:
        redirect_and_final = (
            "HTTP/1.1 301 Moved Permanently\r\n"
            "Location: https://jsnb.org/\r\n\r\n"
            + VALID_HTTP11_HEADERS
        )
        validate_ui_response(redirect_and_final, VALID_BODY)

    def test_rejects_non_200_status(self) -> None:
        headers = VALID_HTTP11_HEADERS.replace("200 OK", "502 Bad Gateway")
        with self.assertRaisesRegex(UIValidationError, "expected HTTP 200, got HTTP 502"):
            validate_ui_response(headers, VALID_BODY)

    def test_rejects_missing_coop(self) -> None:
        headers = (
            "HTTP/1.1 200 OK\r\n"
            "Content-Type: text/html\r\n"
            "Cross-Origin-Embedder-Policy: require-corp\r\n\r\n"
        )
        with self.assertRaisesRegex(UIValidationError, "missing Cross-Origin-Opener-Policy"):
            validate_ui_response(headers, VALID_BODY)

    def test_rejects_invalid_coop_value(self) -> None:
        headers = VALID_HTTP11_HEADERS.replace(
            "Cross-Origin-Opener-Policy: same-origin",
            "Cross-Origin-Opener-Policy: unsafe-none",
        )
        with self.assertRaisesRegex(UIValidationError, "expected Cross-Origin-Opener-Policy 'same-origin'"):
            validate_ui_response(headers, VALID_BODY)

    def test_rejects_missing_coep(self) -> None:
        headers = (
            "HTTP/1.1 200 OK\r\n"
            "Content-Type: text/html\r\n"
            "Cross-Origin-Opener-Policy: same-origin\r\n\r\n"
        )
        with self.assertRaisesRegex(UIValidationError, "missing Cross-Origin-Embedder-Policy"):
            validate_ui_response(headers, VALID_BODY)

    def test_rejects_invalid_coep_value(self) -> None:
        headers = VALID_HTTP11_HEADERS.replace(
            "Cross-Origin-Embedder-Policy: require-corp",
            "Cross-Origin-Embedder-Policy: credentialless",
        )
        with self.assertRaisesRegex(UIValidationError, "expected Cross-Origin-Embedder-Policy 'require-corp'"):
            validate_ui_response(headers, VALID_BODY)

    def test_rejects_body_missing_root_element(self) -> None:
        invalid_body = "<html><body><h1>Error Page</h1></body></html>"
        with self.assertRaisesRegex(UIValidationError, "does not contain '<div id=\"root\">'"):
            validate_ui_response(VALID_HTTP11_HEADERS, invalid_body)

    def test_cli_files_mode(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            headers_path = Path(temp_dir) / "headers.txt"
            body_path = Path(temp_dir) / "body.html"
            headers_path.write_text(VALID_HTTP11_HEADERS, encoding="utf-8")
            body_path.write_text(VALID_BODY, encoding="utf-8")

            script_path = Path(__file__).resolve().parents[1] / "validate_deploy_ui.py"
            result = subprocess.run(
                [sys.executable, str(script_path), "--headers-file", str(headers_path), "--body-file", str(body_path)],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("Deployment UI response: OK", result.stdout)

    def test_cli_stdin_mode(self) -> None:
        combined = VALID_HTTP2_HEADERS + VALID_BODY
        script_path = Path(__file__).resolve().parents[1] / "validate_deploy_ui.py"
        result = subprocess.run(
            [sys.executable, str(script_path)],
            input=combined,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Deployment UI response: OK", result.stdout)


if __name__ == "__main__":
    unittest.main()
