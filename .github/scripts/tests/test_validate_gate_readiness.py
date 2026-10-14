from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from validate_gate_readiness import ReadinessError, validate_readiness  # noqa: E402


class ValidateGateReadinessTests(unittest.TestCase):
    def test_accepts_valid_readiness_payload(self) -> None:
        payload = {
            "status": "ok",
            "app": "JS Notebook API",
            "version": "0.3.1",
            "environment": "production",
            "components": [
                {"name": "database", "status": "ok", "detail": None}
            ],
        }
        # Should not raise
        validate_readiness(payload)

    def test_rejects_non_ok_top_level_status(self) -> None:
        payload = {
            "status": "error",
            "components": [{"name": "database", "status": "ok"}],
        }
        with self.assertRaisesRegex(ReadinessError, "top-level status"):
            validate_readiness(payload)

    def test_rejects_missing_database_component(self) -> None:
        payload = {
            "status": "ok",
            "components": [{"name": "cache", "status": "ok"}],
        }
        with self.assertRaisesRegex(ReadinessError, "missing the 'database' component"):
            validate_readiness(payload)

    def test_rejects_database_component_with_error(self) -> None:
        payload = {
            "status": "ok",
            "components": [
                {"name": "database", "status": "error", "detail": "connection refused"}
            ],
        }
        with self.assertRaisesRegex(ReadinessError, "database component status is 'error'"):
            validate_readiness(payload)

    def test_rejects_non_list_components(self) -> None:
        payload = {
            "status": "ok",
            "components": "not-a-list",
        }
        with self.assertRaisesRegex(ReadinessError, "must be a list"):
            validate_readiness(payload)

    def test_rejects_non_dict_payload(self) -> None:
        with self.assertRaisesRegex(ReadinessError, "must be a JSON object"):
            validate_readiness(["not", "an", "object"])


if __name__ == "__main__":
    unittest.main()
