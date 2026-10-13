"""Precision and identity boundary tests for secret-safe Watch E2E evidence.

Synthetic input only. No physical device result, Watch APK, or production target.
"""

import datetime as dt
import importlib.util
from pathlib import Path
import unittest


SOURCE = Path(__file__).resolve().parents[1] / "tools" / "validate-watch-e2e-evidence.py"
SPEC = importlib.util.spec_from_file_location("raise_e2e_boundary_matrix", SOURCE)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("Watch E2E validator unavailable")
validator = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(validator)

SHA = "8f719bb273f9b997848864f342598e7df5f090e5"
UTC = dt.timezone.utc


def evidence(**replacements):
    result = {
        "schema_version": 2,
        "recorded_at_utc": "2026-10-03T23:40:00Z",
        "app_version": "1.5.2",
        "source_revision": SHA,
        "outcome": "success",
        "input_length_chars": 24,
        "latency_ms": 800,
        "route": "quick_ai",
        "status": "ok",
        "execution_enabled": False,
        "execution_reason_present": False,
        "answer_present": True,
    }
    result.update(replacements)
    return result


class WatchE2eTimeProvenanceMatrix(unittest.TestCase):
    def test_age_exactly_at_limit_is_inclusive(self):
        at_limit = dt.datetime(2026, 10, 3, 23, 45, tzinfo=UTC)
        report = validator.validate_evidence(
            evidence(), now_utc=at_limit, max_age_seconds=300
        )
        self.assertTrue(report["valid"])

    def test_age_one_microsecond_past_limit_is_rejected(self):
        past_limit = dt.datetime(2026, 10, 3, 23, 45, 0, 1, tzinfo=UTC)
        with self.assertRaisesRegex(validator.EvidenceError, "evidence age"):
            validator.validate_evidence(
                evidence(), now_utc=past_limit, max_age_seconds=300
            )

    def test_future_clock_skew_at_exact_60_seconds_is_permitted(self):
        clock = dt.datetime(2026, 10, 3, 23, 39, tzinfo=UTC)
        report = validator.validate_evidence(
            evidence(), now_utc=clock, max_age_seconds=0
        )
        self.assertTrue(report["valid"])

    def test_future_clock_skew_over_limit_by_microsecond_is_rejected(self):
        clock = dt.datetime(2026, 10, 3, 23, 38, 59, 999999, tzinfo=UTC)
        with self.assertRaisesRegex(validator.EvidenceError, "in the future"):
            validator.validate_evidence(
                evidence(), now_utc=clock, max_age_seconds=300
            )

    def test_operator_clock_offset_does_not_change_age(self):
        amsterdam = dt.timezone(dt.timedelta(hours=2))
        clock = dt.datetime(2026, 10, 4, 1, 43, tzinfo=amsterdam)
        report = validator.validate_evidence(
            evidence(), now_utc=clock, max_age_seconds=180
        )
        self.assertTrue(report["valid"])
        self.assertEqual(report["recorded_at_utc"], "2026-10-03T23:40:00Z")

    def test_source_revision_compared_case_insensitively(self):
        report = validator.validate_evidence(
            evidence(source_revision=SHA.upper()),
            expect_source_revision="  " + SHA.upper() + "  ",
        )
        self.assertEqual(report["source_revision"], SHA)

    def test_unzoned_evidence_timestamp_is_invalid(self):
        with self.assertRaisesRegex(validator.EvidenceError, "include a timezone"):
            validator.validate_evidence(
                evidence(recorded_at_utc="2026-10-03T23:40:00")
            )

    def test_unzoned_operator_clock_cannot_validate_freshness(self):
        with self.assertRaisesRegex(validator.EvidenceError, "now_utc must include"):
            validator.validate_evidence(
                evidence(), now_utc=dt.datetime(2026, 10, 3, 23, 40),
                max_age_seconds=300,
            )

    def test_subsecond_offset_is_normalized_without_rounding_up(self):
        report = validator.validate_evidence(
            evidence(recorded_at_utc="2026-10-04T01:40:00.999999+02:00")
        )
        self.assertEqual(
            report["recorded_at_utc"], "2026-10-03T23:40:00.999999Z"
        )

    def test_boolean_counts_do_not_masquerade_as_integers(self):
        for field in ("latency_ms", "input_length_chars"):
            with self.subTest(field=field):
                with self.assertRaisesRegex(
                    validator.EvidenceError, field + " must be"
                ):
                    validator.validate_evidence(evidence(**{field: True}))

    def test_wrong_provenance_fails_even_when_reply_is_present(self):
        with self.assertRaisesRegex(
            validator.EvidenceError, "does not match expected"
        ):
            validator.validate_evidence(
                evidence(source_revision="f" * 40),
                expect_source_revision=SHA,
                require_answer=True,
                expect_route="quick_ai",
            )


if __name__ == "__main__":
    unittest.main()
