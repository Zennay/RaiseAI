import importlib.util
import pathlib
import unittest

MODULE_PATH = pathlib.Path(__file__).resolve().parents[1] / "tools" / "validate-physical-observations.py"
SPEC = importlib.util.spec_from_file_location("physical_observation_validator", MODULE_PATH)
validator = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(validator)


REVISION = "0123456789abcdef0123456789abcdef01234567"
APK = "ab" * 32


def session_payload(**overrides):
    payload = {
        "schema_version": 1,
        "started_at_utc": "2026-10-06T05:00:00Z",
        "watch_serial": "192.0.2.8:5555",
        "watch_model": "SM_L315F",
        "app_version": "1.5.2",
        "source_revision": REVISION,
        "apk_sha256": APK,
        "e2e_passed": True,
        "v1_gate_passed": True,
    }
    payload.update(overrides)
    return payload


def observation_payload(**overrides):
    payload = {
        "schema_version": 1,
        "recorded_at_utc": "2026-10-06T05:45:00Z",
        "watch_serial": "192.0.2.8:5555",
        "app_version": "1.5.2",
        "source_revision": REVISION,
        "apk_sha256": APK,
        "screen_off_tested": True,
        "screen_off_behavior": "Raise trigger was attempted with the display off; observed behavior recorded.",
        "background_tested": True,
        "background_behavior": "Raise AI remained enabled while another Watch surface was foregrounded.",
        "ux_failures_reviewed": True,
        "visible_ux_failures": [],
    }
    payload.update(overrides)
    return payload


class PhysicalObservationValidatorTests(unittest.TestCase):
    def test_accepts_complete_provenance_bound_observations(self):
        result = validator.validate_observations(session_payload(), observation_payload())
        self.assertTrue(result["valid"])
        self.assertTrue(result["quality_evidence_complete"])
        self.assertEqual(result["visible_ux_failure_count"], 0)

    def test_accepts_explicit_ux_failures_without_turning_them_into_a_fake_pass(self):
        result = validator.validate_observations(
            session_payload(),
            observation_payload(visible_ux_failures=["Response state was unclear for about two seconds."]),
        )
        self.assertEqual(result["visible_ux_failure_count"], 1)

    def test_rejects_missing_required_field(self):
        observations = observation_payload()
        observations.pop("background_behavior")
        with self.assertRaisesRegex(validator.ObservationError, "missing observation fields"):
            validator.validate_observations(session_payload(), observations)

    def test_rejects_unexpected_fields(self):
        with self.assertRaisesRegex(validator.ObservationError, "unexpected observation fields"):
            validator.validate_observations(
                session_payload(),
                observation_payload(response_text="must not be captured here"),
            )

    def test_rejects_mixed_source_identity(self):
        with self.assertRaisesRegex(validator.ObservationError, "source_revision does not match"):
            validator.validate_observations(
                session_payload(),
                observation_payload(source_revision="f" * 40),
            )

    def test_rejects_mixed_apk_identity(self):
        with self.assertRaisesRegex(validator.ObservationError, "apk_sha256 does not match"):
            validator.validate_observations(
                session_payload(),
                observation_payload(apk_sha256="cd" * 32),
            )

    def test_rejects_unperformed_screen_off_check(self):
        with self.assertRaisesRegex(validator.ObservationError, "screen_off_tested must be true"):
            validator.validate_observations(
                session_payload(),
                observation_payload(screen_off_tested=False),
            )

    def test_rejects_unreviewed_ux_failures(self):
        with self.assertRaisesRegex(validator.ObservationError, "ux_failures_reviewed must be true"):
            validator.validate_observations(
                session_payload(),
                observation_payload(ux_failures_reviewed=False),
            )

    def test_rejects_blank_behavior_observation(self):
        with self.assertRaisesRegex(validator.ObservationError, "background_behavior"):
            validator.validate_observations(
                session_payload(),
                observation_payload(background_behavior="   "),
            )

    def test_rejects_observations_before_session_start(self):
        with self.assertRaisesRegex(validator.ObservationError, "before the physical session started"):
            validator.validate_observations(
                session_payload(),
                observation_payload(recorded_at_utc="2026-10-06T04:59:59Z"),
            )

    def test_rejects_non_string_failure_entry(self):
        with self.assertRaisesRegex(validator.ObservationError, r"visible_ux_failures\[0\]"):
            validator.validate_observations(
                session_payload(),
                observation_payload(visible_ux_failures=[{"kind": "slow"}]),
            )


if __name__ == "__main__":
    unittest.main()
