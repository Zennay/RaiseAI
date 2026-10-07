import contextlib
import importlib.util
import io
import json
import os
import pathlib
import stat
import tempfile
import unittest
from unittest import mock

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
        self.assertEqual(result["schema_version"], 1)
        self.assertTrue(result["valid"])
        self.assertTrue(result["quality_evidence_complete"])
        self.assertEqual(result["visible_ux_failure_count"], 0)

    def test_loader_rejects_duplicate_observation_fields(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / "operator-observations.json"
            path.write_text('{"schema_version":1,"schema_version":1}', encoding="utf-8")
            with self.assertRaisesRegex(validator.ObservationError, "duplicate JSON field: schema_version"):
                validator.load_json_document(path, "observations")

    def test_loader_rejects_oversized_session(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / "session.json"
            path.write_bytes(b" " * (validator.MAX_JSON_BYTES + 1))
            with self.assertRaisesRegex(validator.ObservationError, "session exceeds maximum size"):
                validator.load_json_document(path, "session")

    def test_loader_rejects_invalid_utf8_observations(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / "operator-observations.json"
            path.write_bytes(bytes((0x7B, 0xFF, 0x7D)))
            with self.assertRaisesRegex(validator.ObservationError, "observations must be valid UTF-8"):
                validator.load_json_document(path, "observations")

    def test_loader_reads_same_inode_when_path_is_replaced_after_open(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            path = root / "session.json"
            replacement = root / "replacement.json"
            original = session_payload(watch_serial="original-watch")
            forged = session_payload(watch_serial="forged-watch")
            path.write_text(json.dumps(original), encoding="utf-8")
            replacement.write_text(json.dumps(forged), encoding="utf-8")

            real_open = validator.os.open

            def open_then_replace(target, flags):
                fd = real_open(target, flags)
                pathlib.Path(target).unlink()
                replacement.rename(target)
                return fd

            with mock.patch.object(validator.os, "open", side_effect=open_then_replace):
                loaded = validator.load_json_document(path, "session")

            self.assertEqual(loaded["watch_serial"], "original-watch")
            self.assertEqual(
                json.loads(path.read_text(encoding="utf-8"))["watch_serial"],
                "forged-watch",
            )

    @unittest.skipUnless(hasattr(os, "O_NONBLOCK"), "O_NONBLOCK unavailable")
    def test_loader_sets_nonblocking_before_file_type_validation(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / "session.json"
            path.write_text(json.dumps(session_payload()), encoding="utf-8")
            real_open = validator.os.open

            def require_nonblocking(target, flags):
                self.assertTrue(flags & os.O_NONBLOCK)
                return real_open(target, flags)

            with mock.patch.object(validator.os, "open", side_effect=require_nonblocking):
                loaded = validator.load_json_document(path, "session")

            self.assertEqual(loaded["schema_version"], 1)

    def test_loader_rejects_symlink_input(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            target = root / "session-real.json"
            target.write_text(json.dumps(session_payload()), encoding="utf-8")
            path = root / "session.json"
            path.symlink_to(target)
            with self.assertRaises(OSError):
                validator.load_json_document(path, "session")

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

    def test_rejects_unsupported_session_schema(self):
        with self.assertRaisesRegex(validator.ObservationError, "session schema_version must equal 1"):
            validator.validate_observations(
                session_payload(schema_version=2),
                observation_payload(),
            )

    def test_rejects_boolean_observation_schema(self):
        with self.assertRaisesRegex(validator.ObservationError, "schema_version must equal 1"):
            validator.validate_observations(
                session_payload(),
                observation_payload(schema_version=True),
            )

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

    def test_canonicalizes_recorded_timestamp_to_utc(self):
        result = validator.validate_observations(
            session_payload(),
            observation_payload(recorded_at_utc="2026-10-06T07:45:00+02:00"),
        )
        self.assertEqual(result["recorded_at_utc"], "2026-10-06T05:45:00Z")

    def test_preserves_recorded_timestamp_subseconds(self):
        result = validator.validate_observations(
            session_payload(started_at_utc="2026-10-06T05:00:00.900000Z"),
            observation_payload(recorded_at_utc="2026-10-06T05:00:00.950000Z"),
        )
        self.assertEqual(result["recorded_at_utc"], "2026-10-06T05:00:00.950000Z")

    def test_rejects_non_string_failure_entry(self):
        with self.assertRaisesRegex(validator.ObservationError, r"visible_ux_failures\[0\]"):
            validator.validate_observations(
                session_payload(),
                observation_payload(visible_ux_failures=[{"kind": "slow"}]),
            )


    def test_quality_summary_has_exact_secret_safe_shape(self):
        result = validator.validate_observations(session_payload(), observation_payload())
        self.assertEqual(
            set(result),
            {
                "schema_version",
                "valid",
                "quality_evidence_complete",
                "recorded_at_utc",
                "watch_identity_match",
                "app_version",
                "source_revision",
                "apk_sha256",
                "screen_off_tested",
                "background_tested",
                "ux_failures_reviewed",
                "visible_ux_failure_count",
            },
        )
        serialized = json.dumps(result, sort_keys=True)
        for forbidden in (
            "watch_serial",
            "screen_off_behavior",
            "background_behavior",
            "visible_ux_failures",
            "transcript",
            "answer_text",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, serialized)

    def test_cli_success_returns_machine_readable_summary(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            session = root / "session.json"
            observations = root / "operator-observations.json"
            session.write_text(json.dumps(session_payload()), encoding="utf-8")
            observations.write_text(json.dumps(observation_payload()), encoding="utf-8")
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                code = validator.main([str(session), str(observations)])
        self.assertEqual(code, 0)
        payload = json.loads(output.getvalue())
        self.assertTrue(payload["quality_evidence_complete"])
        self.assertNotIn("screen_off_behavior", payload)
        self.assertNotIn("background_behavior", payload)

    def test_cli_output_file_is_secret_safe_and_refuses_overwrite(self):
        secret = "screen-off note that must stay local"
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            session = root / "session.json"
            observations = root / "operator-observations.json"
            result = root / "quality-result.json"
            session.write_text(json.dumps(session_payload()), encoding="utf-8")
            observations.write_text(
                json.dumps(observation_payload(screen_off_behavior=secret)),
                encoding="utf-8",
            )
            first_output = io.StringIO()
            with contextlib.redirect_stdout(first_output):
                first = validator.main([str(session), str(observations), "--output", str(result)])
            self.assertEqual(first, 0)
            persisted = result.read_text(encoding="utf-8")
            self.assertEqual(stat.S_IMODE(result.stat().st_mode), 0o600)
            self.assertNotIn(secret, persisted)
            self.assertNotIn(session_payload()["watch_serial"], persisted)
            self.assertTrue(json.loads(persisted)["quality_evidence_complete"])

            second_output = io.StringIO()
            with contextlib.redirect_stdout(second_output):
                second = validator.main([str(session), str(observations), "--output", str(result)])
            self.assertEqual(second, 1)
            self.assertIn("refusing to overwrite", second_output.getvalue())

    def test_cli_output_publish_failure_leaves_no_partial_result(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            session = root / "session.json"
            observations = root / "operator-observations.json"
            result = root / "quality-result.json"
            session.write_text(json.dumps(session_payload()), encoding="utf-8")
            observations.write_text(json.dumps(observation_payload()), encoding="utf-8")

            failed_output = io.StringIO()
            with mock.patch.object(
                validator.os,
                "link",
                side_effect=OSError("simulated publish failure"),
            ), contextlib.redirect_stdout(failed_output):
                failed = validator.main(
                    [str(session), str(observations), "--output", str(result)]
                )

            self.assertEqual(failed, 1)
            self.assertFalse(result.exists())
            self.assertEqual(list(root.glob(".quality-result.json.*.tmp")), [])
            self.assertIn("simulated publish failure", failed_output.getvalue())

            success_output = io.StringIO()
            with contextlib.redirect_stdout(success_output):
                success = validator.main(
                    [str(session), str(observations), "--output", str(result)]
                )

            self.assertEqual(success, 0, success_output.getvalue())
            self.assertTrue(json.loads(result.read_text(encoding="utf-8"))["quality_evidence_complete"])

    def test_cli_output_refuses_broken_symlink_without_creating_target(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            session = root / "session.json"
            observations = root / "operator-observations.json"
            result = root / "quality-result.json"
            target = root / "unexpected-target.json"
            session.write_text(json.dumps(session_payload()), encoding="utf-8")
            observations.write_text(json.dumps(observation_payload()), encoding="utf-8")
            result.symlink_to(target)

            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                code = validator.main([str(session), str(observations), "--output", str(result)])

            self.assertEqual(code, 1)
            self.assertTrue(result.is_symlink())
            self.assertFalse(target.exists())
            self.assertIn("refusing to overwrite", output.getvalue())

    def test_cli_failure_does_not_echo_sensitive_observation_values(self):
        secret = "private spoken content must never be echoed"
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            session = root / "session.json"
            observations = root / "operator-observations.json"
            session.write_text(json.dumps(session_payload()), encoding="utf-8")
            observations.write_text(
                json.dumps(observation_payload(transcript=secret)),
                encoding="utf-8",
            )
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                code = validator.main([str(session), str(observations)])
        self.assertEqual(code, 1)
        payload = json.loads(output.getvalue())
        self.assertFalse(payload["valid"])
        self.assertNotIn(secret, output.getvalue())

if __name__ == "__main__":
    unittest.main()
