"""Regression guard: public physical-observation summaries must omit raw Watch identity and notes.

The original source data intentionally contains a serial and operator free-text.
Only the compact allowlisted summary may leave the operator's machine.
"""
import datetime as dt
import importlib.util
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "raise_physical_observations", ROOT / "tools" / "validate-physical-observations.py"
)
module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(module)

ALLOWED_PUBLIC_KEYS = frozenset({
    "schema_version", "valid", "quality_evidence_complete",
    "recorded_at_utc", "watch_identity_match", "app_version",
    "source_revision", "apk_sha256", "screen_off_tested",
    "background_tested", "ux_failures_reviewed", "visible_ux_failure_count",
})


class PublicObservationSummaryTest(unittest.TestCase):
    def test_private_observations_never_enter_public_summary(self):
        started = dt.datetime(2026, 10, 8, 1, 0, tzinfo=dt.timezone.utc)
        serial = "PRIVATE_WATCH_SERIAL_SENTINEL"
        screen_note = "PRIVATE_SCREEN_OBSERVATION_SENTINEL"
        background_note = "PRIVATE_BACKGROUND_OBSERVATION_SENTINEL"
        failure_note = "PRIVATE_UX_FAILURE_SENTINEL"
        session = {
            "schema_version": 1, "watch_serial": serial,
            "app_version": "1.5.2", "source_revision": "a" * 40,
            "apk_sha256": "b" * 64, "started_at_utc": started.isoformat(),
        }
        observations = {
            "schema_version": 1, "recorded_at_utc": (started + dt.timedelta(minutes=1)).isoformat(),
            "watch_serial": serial, "app_version": "1.5.2",
            "source_revision": "a" * 40, "apk_sha256": "b" * 64,
            "screen_off_tested": True, "screen_off_behavior": screen_note,
            "background_tested": True, "background_behavior": background_note,
            "ux_failures_reviewed": True, "visible_ux_failures": [failure_note],
        }
        result = module.validate_observations(
            session, observations, now_utc=started + dt.timedelta(minutes=2)
        )
        self.assertEqual(set(result), ALLOWED_PUBLIC_KEYS)
        self.assertIs(result["valid"], True)
        self.assertIs(result["quality_evidence_complete"], True)
        self.assertEqual(result["visible_ux_failure_count"], 1)
        serialized = __import__("json").dumps(result)
        for sentinel in (serial, screen_note, background_note, failure_note):
            with self.subTest(sentinel=sentinel):
                self.assertNotIn(sentinel, serialized)


if __name__ == "__main__":
    unittest.main()
