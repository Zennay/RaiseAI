import importlib.util
import json
import pathlib
import tempfile
import unittest

GENERATOR_PATH = pathlib.Path(__file__).resolve().parents[1] / "tools" / "create-physical-observation-template.py"
GENERATOR_SPEC = importlib.util.spec_from_file_location("physical_observation_template", GENERATOR_PATH)
generator = importlib.util.module_from_spec(GENERATOR_SPEC)
assert GENERATOR_SPEC.loader is not None
GENERATOR_SPEC.loader.exec_module(generator)

VALIDATOR_PATH = pathlib.Path(__file__).resolve().parents[1] / "tools" / "validate-physical-observations.py"
VALIDATOR_SPEC = importlib.util.spec_from_file_location("physical_observation_validator_for_template", VALIDATOR_PATH)
validator = importlib.util.module_from_spec(VALIDATOR_SPEC)
assert VALIDATOR_SPEC.loader is not None
VALIDATOR_SPEC.loader.exec_module(validator)

REVISION = "0123456789abcdef0123456789abcdef01234567"
APK = "ab" * 32


def session_payload(**overrides):
    payload = {
        "schema_version": 1,
        "started_at_utc": "2026-10-06T05:00:00Z",
        "watch_serial": "192.0.2.8:5555",
        "app_version": "1.5.2",
        "source_revision": REVISION,
        "apk_sha256": APK,
    }
    payload.update(overrides)
    return payload


class PhysicalObservationTemplateTests(unittest.TestCase):
    def test_template_copies_exact_session_identity_and_fails_closed(self):
        session = session_payload()
        payload = generator.build_template(session, recorded_at_utc="2026-10-06T05:45:00Z")
        self.assertEqual(payload["watch_serial"], session["watch_serial"])
        self.assertEqual(payload["source_revision"], REVISION)
        self.assertEqual(payload["apk_sha256"], APK)
        self.assertFalse(payload["screen_off_tested"])
        self.assertFalse(payload["background_tested"])
        self.assertFalse(payload["ux_failures_reviewed"])
        with self.assertRaises(validator.ObservationError):
            validator.validate_observations(session, payload)

    def test_rejects_missing_session_identity(self):
        session = session_payload()
        session.pop("apk_sha256")
        with self.assertRaisesRegex(generator.TemplateError, "apk_sha256"):
            generator.build_template(session)

    def test_rejects_unsupported_session_schema(self):
        with self.assertRaisesRegex(generator.TemplateError, "session schema_version must equal 1"):
            generator.build_template(
                session_payload(schema_version=2),
                recorded_at_utc="2026-10-06T05:45:00Z",
            )

    def test_rejects_boolean_session_schema(self):
        with self.assertRaisesRegex(generator.TemplateError, "session schema_version must equal 1"):
            generator.build_template(
                session_payload(schema_version=True),
                recorded_at_utc="2026-10-06T05:45:00Z",
            )

    def test_cli_creates_file_beside_session_and_refuses_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            session_path = root / "session.json"
            session_path.write_text(json.dumps(session_payload()), encoding="utf-8")
            first = generator.main([str(session_path)])
            output = root / "operator-observations.json"
            self.assertEqual(first, 0)
            self.assertTrue(output.exists())
            second = generator.main([str(session_path)])
            self.assertEqual(second, 1)

    def test_cli_refuses_broken_symlink_without_creating_target(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            session_path = root / "session.json"
            output = root / "operator-observations.json"
            target = root / "unexpected-target.json"
            session_path.write_text(json.dumps(session_payload()), encoding="utf-8")
            output.symlink_to(target)

            code = generator.main([str(session_path)])

            self.assertEqual(code, 1)
            self.assertTrue(output.is_symlink())
            self.assertFalse(target.exists())

    def test_normalizes_uppercase_hashes(self):
        payload = generator.build_template(
            session_payload(source_revision=REVISION.upper(), apk_sha256=APK.upper()),
            recorded_at_utc="2026-10-06T05:45:00Z",
        )
        self.assertEqual(payload["source_revision"], REVISION)
        self.assertEqual(payload["apk_sha256"], APK)

    def test_normalizes_recorded_timestamp_to_utc(self):
        payload = generator.build_template(
            session_payload(),
            recorded_at_utc="2026-10-06T07:45:00+02:00",
        )
        self.assertEqual(payload["recorded_at_utc"], "2026-10-06T05:45:00Z")

    def test_rejects_invalid_session_start_timestamp(self):
        with self.assertRaisesRegex(generator.TemplateError, "session started_at_utc must be ISO-8601"):
            generator.build_template(
                session_payload(started_at_utc="not-a-timestamp"),
                recorded_at_utc="2026-10-06T05:45:00Z",
            )

    def test_rejects_session_start_without_timezone(self):
        with self.assertRaisesRegex(generator.TemplateError, "session started_at_utc must include a timezone"):
            generator.build_template(
                session_payload(started_at_utc="2026-10-06T05:00:00"),
                recorded_at_utc="2026-10-06T05:45:00Z",
            )

    def test_rejects_recorded_timestamp_before_session_start(self):
        with self.assertRaisesRegex(generator.TemplateError, "must not be before the physical session started"):
            generator.build_template(
                session_payload(),
                recorded_at_utc="2026-10-06T04:59:59Z",
            )

    def test_preserves_subsecond_ordering_in_canonical_utc(self):
        payload = generator.build_template(
            session_payload(started_at_utc="2026-10-06T05:00:00.900000Z"),
            recorded_at_utc="2026-10-06T07:00:00.950000+02:00",
        )
        self.assertEqual(payload["recorded_at_utc"], "2026-10-06T05:00:00.950000Z")
        result = validator.validate_observations(
            session_payload(started_at_utc="2026-10-06T05:00:00.900000Z"),
            {
                **payload,
                "screen_off_tested": True,
                "screen_off_behavior": "Display-off behavior observed.",
                "background_tested": True,
                "background_behavior": "Background behavior observed.",
                "ux_failures_reviewed": True,
            },
        )
        self.assertTrue(result["valid"])


if __name__ == "__main__":
    unittest.main()
