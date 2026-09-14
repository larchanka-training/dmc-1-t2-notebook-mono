from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from validate_deploy_health import HealthError, validate_health  # noqa: E402


class ValidateDeployHealthTests(unittest.TestCase):
    def test_accepts_ok_response_from_expected_environment(self) -> None:
        validate_health(
            {"status": "ok", "environment": "production"},
            expected_environment="production",
        )

    def test_rejects_non_ok_status(self) -> None:
        with self.assertRaisesRegex(HealthError, "status"):
            validate_health(
                {"status": "error", "environment": "production"},
                expected_environment="production",
            )

    def test_rejects_wrong_environment(self) -> None:
        with self.assertRaisesRegex(HealthError, "environment"):
            validate_health(
                {"status": "ok", "environment": "staging"},
                expected_environment="production",
            )

    def test_rejects_non_object_response(self) -> None:
        with self.assertRaisesRegex(HealthError, "JSON object"):
            validate_health([], expected_environment="production")


if __name__ == "__main__":
    unittest.main()
