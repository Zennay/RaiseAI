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
        "schema_version": 2,
        "recorded_at_utc": "2026-10-03T23:40:00Z",
        "app_version": "1.5.1",
        "source_revision": "0123456789abcdef0123456789abcdef01234567",
        "outcome": "success",
        "input_length_chars": 18,
        "latency_ms": 742,
        "route": "quick_ai",
        "status": "answered",
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
            expect_status="answered",
            max_latency_ms=2_000,
            max_age_seconds=300,
            require_answer=True,
            expect_app_version="1.5.1",
            expect_source_revision="0123456789abcdef0123456789abcdef01234567",
            now_utc=dt.datetime(2026, 10, 3, 23, 42, tzinfo=dt.timezone.utc),
        )
        self.assertTrue(result["valid"])
        self.assertEqual(result["route"], "quick_ai")

    def test_rejects_duplicate_json_fields_before_validation(self):
        with self.assertRaisesRegex(validator.EvidenceError, "duplicate JSON field: route"):
            validator._strict_json_loads(
                '{"schema_version":2,"route":"quick_ai","route":"deep_ai"}'
            )

    def test_rejects_unexpected_field_to_keep_evidence_secret_safe(self):
        with self.assertRaisesRegex(validator.EvidenceError, "unexpected evidence fields"):
            validator.validate_evidence(success_payload(answer_text="must never be serialized"))

    def test_rejects_boolean_schema_version(self):
        with self.assertRaisesRegex(validator.EvidenceError, "schema_version must equal 2"):
            validator.validate_evidence(success_payload(schema_version=True))

    def test_canonicalizes_recorded_timestamp_to_utc(self):
        result = validator.validate_evidence(
            success_payload(recorded_at_utc="2026-10-04T01:40:00+02:00")
        )
        self.assertEqual(result["recorded_at_utc"], "2026-10-03T23:40:00Z")

    def test_preserves_recorded_timestamp_subseconds(self):
        result = validator.validate_evidence(
            success_payload(recorded_at_utc="2026-10-03T23:40:00.950000Z")
        )
        self.assertEqual(result["recorded_at_utc"], "2026-10-03T23:40:00.950000Z")

    def test_rejects_unknown_route(self):
        with self.assertRaisesRegex(validator.EvidenceError, "unknown route"):
            validator.validate_evidence(success_payload(route="unknown"))

    def test_rejects_unknown_success_status(self):
        with self.assertRaisesRegex(validator.EvidenceError, "status must be answered or routed"):
            validator.validate_evidence(success_payload(status="ok"))

    def test_rejects_answered_status_without_answer(self):
        with self.assertRaisesRegex(validator.EvidenceError, "same gateway outcome"):
            validator.validate_evidence(
                success_payload(status="answered", answer_present=False)
            )

    def test_rejects_routed_status_with_answer(self):
        with self.assertRaisesRegex(validator.EvidenceError, "same gateway outcome"):
            validator.validate_evidence(
                success_payload(status="routed", answer_present=True)
            )

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

    def test_rejects_wrong_app_version(self):
        with self.assertRaisesRegex(validator.EvidenceError, "app_version"):
            validator.validate_evidence(
                success_payload(),
                expect_app_version="1.5.0",
            )

    def test_rejects_wrong_source_revision(self):
        with self.assertRaisesRegex(validator.EvidenceError, "source_revision"):
            validator.validate_evidence(
                success_payload(),
                expect_source_revision="fedcba9876543210fedcba9876543210fedcba98",
            )

    def test_rejects_non_git_source_revision(self):
        with self.assertRaisesRegex(validator.EvidenceError, "40-character Git SHA"):
            validator.validate_evidence(
                success_payload(source_revision="unknown"),
            )

    def test_failure_evidence_is_not_a_passing_gate(self):
        failure = {
            "schema_version": 2,
            "recorded_at_utc": "2026-10-03T23:40:00Z",
            "app_version": "1.5.1",
            "source_revision": "0123456789abcdef0123456789abcdef01234567",
            "outcome": "failure",
            "input_length_chars": 18,
            "latency_ms": 1200,
            "error_code": "gateway_http_503",
        }
        with self.assertRaisesRegex(validator.EvidenceError, "Watch E2E request failed"):
            validator.validate_evidence(failure)


if __name__ == "__main__":
    unittest.main()
