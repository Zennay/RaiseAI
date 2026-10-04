import datetime as dt
import importlib.util
import pathlib
import unittest

MODULE_PATH = pathlib.Path(__file__).resolve().parents[1] / "tools" / "validate-watch-e2e-evidence.py"
SPEC = importlib.util.spec_from_file_location("watch_e2e_validator", MODULE_PATH)
validator = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(validator)


def success_payload(**overrides):
    payload = {
        "schema_version": 1,
        "recorded_at_utc": "2026-10-03T23:40:00Z",
        "outcome": "success",
        "input_length_chars": 18,
        "latency_ms": 742,
        "route": "quick_ai",
        "status": "ok",
        "execution_enabled": False,
        "execution_reason_present": False,
        "answer_present": True,
    }
    payload.update(overrides)
    return payload


class WatchE2eEvidenceValidatorTests(unittest.TestCase):
    def test_accepts_expected_success(self):
        result = validator.validate_evidence(
            success_payload(),
            expect_route="quick_ai",
            expect_status="ok",
            max_latency_ms=2_000,
            max_age_seconds=300,
            require_answer=True,
            now_utc=dt.datetime(2026, 10, 3, 23, 42, tzinfo=dt.timezone.utc),
        )
        self.assertTrue(result["valid"])
        self.assertEqual(result["route"], "quick_ai")

    def test_rejects_unexpected_field_to_keep_evidence_secret_safe(self):
        with self.assertRaisesRegex(validator.EvidenceError, "unexpected evidence fields"):
            validator.validate_evidence(success_payload(answer_text="must never be serialized"))

    def test_rejects_unknown_route(self):
        with self.assertRaisesRegex(validator.EvidenceError, "unknown route"):
            validator.validate_evidence(success_payload(route="unknown"))

    def test_rejects_excessive_latency(self):
        with self.assertRaisesRegex(validator.EvidenceError, "exceeds maximum"):
            validator.validate_evidence(success_payload(latency_ms=15_001), max_latency_ms=15_000)

    def test_rejects_route_mismatch(self):
        with self.assertRaisesRegex(validator.EvidenceError, "does not match expected"):
            validator.validate_evidence(success_payload(route="deep_ai"), expect_route="quick_ai")

    def test_rejects_stale_evidence(self):
        with self.assertRaisesRegex(validator.EvidenceError, "evidence age"):
            validator.validate_evidence(
                success_payload(recorded_at_utc="2026-10-03T23:30:00Z"),
                max_age_seconds=300,
                now_utc=dt.datetime(2026, 10, 3, 23, 40, tzinfo=dt.timezone.utc),
            )

    def test_accepts_small_future_clock_skew(self):
        result = validator.validate_evidence(
            success_payload(recorded_at_utc="2026-10-03T23:40:45Z"),
            max_age_seconds=300,
            now_utc=dt.datetime(2026, 10, 3, 23, 40, tzinfo=dt.timezone.utc),
        )
        self.assertTrue(result["valid"])

    def test_rejects_large_future_timestamp(self):
        with self.assertRaisesRegex(validator.EvidenceError, "in the future"):
            validator.validate_evidence(
                success_payload(recorded_at_utc="2026-10-03T23:42:00Z"),
                max_age_seconds=300,
                now_utc=dt.datetime(2026, 10, 3, 23, 40, tzinfo=dt.timezone.utc),
            )

    def test_failure_evidence_is_not_a_passing_gate(self):
        failure = {
            "schema_version": 1,
            "recorded_at_utc": "2026-10-03T23:40:00Z",
            "outcome": "failure",
            "input_length_chars": 18,
            "latency_ms": 1200,
            "error_code": "gateway_http_503",
        }
        with self.assertRaisesRegex(validator.EvidenceError, "Watch E2E request failed"):
            validator.validate_evidence(failure)


if __name__ == "__main__":
    unittest.main()
