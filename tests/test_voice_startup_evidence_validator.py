import datetime as dt
import importlib.util
import pathlib
import unittest

MODULE_PATH = pathlib.Path(__file__).resolve().parents[1] / "tools" / "validate-voice-startup-evidence.py"
SPEC = importlib.util.spec_from_file_location("voice_startup_validator", MODULE_PATH)
validator = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(validator)

NOW = dt.datetime(2026, 10, 5, 1, 45, tzinfo=dt.timezone.utc)
REVISION = "a" * 40


def valid_payload(**updates):
    payload = {
        "schema_version": 1,
        "recorded_at_utc": "2026-10-05T01:44:30Z",
        "app_version": "1.5.2",
        "source_revision": REVISION,
        "attempt": 1,
        "listen_request_to_ready_ms": 420,
    }
    payload.update(updates)
    return payload


class VoiceStartupEvidenceValidatorTest(unittest.TestCase):
    def test_accepts_fresh_provenance_bound_metric(self):
        result = validator.validate_evidence(valid_payload(), now=NOW)
        self.assertEqual(420, result["listen_request_to_ready_ms"])
        self.assertEqual(REVISION, result["source_revision"])

    def test_rejects_extra_fields(self):
        with self.assertRaisesRegex(validator.EvidenceError, "unexpected or missing"):
            validator.validate_evidence(valid_payload(transcript="secret"), now=NOW)

    def test_rejects_invalid_revision(self):
        with self.assertRaisesRegex(validator.EvidenceError, "source_revision"):
            validator.validate_evidence(valid_payload(source_revision="main"), now=NOW)

    def test_rejects_negative_latency(self):
        with self.assertRaisesRegex(validator.EvidenceError, "listen_request_to_ready_ms"):
            validator.validate_evidence(
                valid_payload(listen_request_to_ready_ms=-1),
                now=NOW,
            )

    def test_optional_product_threshold_is_fail_closed(self):
        with self.assertRaisesRegex(validator.EvidenceError, "exceeds 400 ms"):
            validator.validate_evidence(
                valid_payload(listen_request_to_ready_ms=420),
                now=NOW,
                max_listen_ready_ms=400,
            )

    def test_rejects_stale_evidence(self):
        with self.assertRaisesRegex(validator.EvidenceError, "stale"):
            validator.validate_evidence(
                valid_payload(recorded_at_utc="2026-10-05T01:30:00Z"),
                now=NOW,
                max_age_seconds=300,
            )


if __name__ == "__main__":
    unittest.main()
