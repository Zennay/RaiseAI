import importlib.util
import json
import pathlib
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

MODULE_PATH = pathlib.Path(__file__).resolve().parents[1] / "tools" / "prepare-physical-share-bundle.py"
SPEC = importlib.util.spec_from_file_location("physical_share_bundle", MODULE_PATH)
bundle = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(bundle)

REVISION = bundle.FROZEN_SOURCE_REVISION
APK_SHA256 = bundle.FROZEN_APK_SHA256
DETECTOR_CONFIG = bundle.FROZEN_DETECTOR_CONFIG


def e2e_payload():
    return {
        "valid": True,
        "outcome": "success",
        "route": "quick_ai",
        "status": "answered",
        "latency_ms": 1200,
        "input_length_chars": 12,
        "answer_present": True,
        "execution_enabled": False,
        "recorded_at_utc": "2026-10-07T12:00:00Z",
        "app_version": "1.5.2",
        "source_revision": REVISION,
    }


def v1_payload():
    return {
        "schema_version": 1,
        "v1_gate_passed": True,
        "evidence_identity": {
            "app_version": "1.5.2",
            "source_revision": REVISION,
            "detector_config": DETECTOR_CONFIG,
        },
        "requirements": {
            "mouth_raise_trials": 30,
            "non_trigger_trials": 100,
            "min_detection_rate": 0.9,
            "max_false_trigger_rate": 0.05,
        },
        "results": {
            "mouth_raise_trials": 30,
            "mouth_raise_detected": 30,
            "detection_rate": 1.0,
            "non_trigger_trials": 100,
            "false_triggers": 0,
            "false_trigger_rate": 0.0,
        },
        "remaining": {
            "mouth_raise_trials": 0,
            "non_trigger_trials": 0,
        },
        "rejected_trial_count": 0,
    }


def quality_payload():
    return {
        "schema_version": 1,
        "valid": True,
        "quality_evidence_complete": True,
        "recorded_at_utc": "2026-10-07T12:05:00Z",
        "watch_identity_match": True,
        "app_version": "1.5.2",
        "source_revision": REVISION,
        "apk_sha256": APK_SHA256,
        "screen_off_tested": True,
        "background_tested": True,
        "ux_failures_reviewed": True,
        "visible_ux_failure_count": 0,
    }


class PhysicalShareBundleTests(unittest.TestCase):
    def write_session(self, root: pathlib.Path):
        session = root / "session"
        session.mkdir()
        payloads = {
            "e2e-result.json": e2e_payload(),
            "v1-result.json": v1_payload(),
            "quality-result.json": quality_payload(),
        }
        for name, payload in payloads.items():
            (session / name).write_text(json.dumps(payload) + "\n", encoding="utf-8")
        return session

    def test_prepare_bundle_writes_only_canonical_summaries(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            session = self.write_session(root)
            output = root / "share"
            bundle.prepare_bundle(session, output)

            self.assertEqual(
                sorted(path.name for path in output.iterdir()),
                sorted(bundle.SUMMARY_FILES),
            )
            self.assertEqual(output.stat().st_mode & 0o777, 0o700)
            for name in bundle.SUMMARY_FILES:
                data = json.loads((output / name).read_text(encoding="utf-8"))
                self.assertIsInstance(data, dict)
                self.assertEqual((output / name).stat().st_mode & 0o777, 0o600)

    def test_partial_os_writes_still_publish_complete_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            session = self.write_session(root)
            output = root / "share"
            real_write = bundle.os.write

            def short_write(fd, data):
                return real_write(fd, data[: max(1, min(len(data), 7))])

            with mock.patch.object(bundle.os, "write", side_effect=short_write):
                bundle.prepare_bundle(session, output)

            for name in bundle.SUMMARY_FILES:
                payload = json.loads((output / name).read_text(encoding="utf-8"))
                self.assertIsInstance(payload, dict)

    def test_cli_publishes_bundle_and_machine_readable_success(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            session = self.write_session(root)
            output = root / "share"

            result = subprocess.run(
                [sys.executable, str(MODULE_PATH), str(session), str(output)],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=5,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stderr, "")
            payload = json.loads(result.stdout)
            self.assertTrue(payload["valid"])
            self.assertEqual(payload["bundle"], str(output))
            self.assertEqual(payload["files"], list(bundle.SUMMARY_FILES))
            self.assertEqual(
                sorted(path.name for path in output.iterdir()),
                sorted(bundle.SUMMARY_FILES),
            )

    def test_cli_failure_is_machine_readable_and_does_not_publish(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            session = self.write_session(root)
            (session / "e2e-result.json").unlink()
            output = root / "share"

            result = subprocess.run(
                [sys.executable, str(MODULE_PATH), str(session), str(output)],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=5,
                check=False,
            )

            self.assertEqual(result.returncode, 1)
            self.assertEqual(result.stderr, "")
            payload = json.loads(result.stdout)
            self.assertFalse(payload["valid"])
            self.assertIn("e2e-result.json", payload["reason"])
            self.assertFalse(output.exists())

    def test_missing_summary_fails_closed_without_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            session = self.write_session(root)
            (session / "v1-result.json").unlink()
            output = root / "share"

            with self.assertRaises(bundle.ShareBundleError):
                bundle.prepare_bundle(session, output)
            self.assertFalse(output.exists())

    def test_symlink_session_directory_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            session = self.write_session(root)
            linked = root / "linked-session"
            linked.symlink_to(session, target_is_directory=True)

            with self.assertRaisesRegex(bundle.ShareBundleError, "session directory must not be a symlink"):
                bundle.prepare_bundle(linked, root / "share")

    def test_symlink_summary_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            session = self.write_session(root)
            source = session / "e2e-result.json"
            target = session / "e2e-real.json"
            source.rename(target)
            source.symlink_to(target)
            output = root / "share"

            with self.assertRaises(bundle.ShareBundleError):
                bundle.prepare_bundle(session, output)
            self.assertFalse(output.exists())

    def test_duplicate_json_field_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            session = self.write_session(root)
            (session / "quality-result.json").write_text(
                '{"schema_version":1,"valid":true,"valid":true}\n',
                encoding="utf-8",
            )
            with self.assertRaises(bundle.ShareBundleError):
                bundle.prepare_bundle(session, root / "share")

    def test_sensitive_fields_are_rejected_recursively(self):
        payload = quality_payload()
        payload["nested"] = {"watch_serial": "secret"}
        with self.assertRaisesRegex(bundle.ShareBundleError, "forbidden field"):
            bundle.validate_summaries(e2e_payload(), v1_payload(), payload)

    def test_unexpected_summary_fields_are_rejected(self):
        bad_e2e = e2e_payload()
        bad_e2e["notes"] = "should never enter the share bundle"
        with self.assertRaisesRegex(bundle.ShareBundleError, "unexpected fields"):
            bundle.validate_summaries(bad_e2e, v1_payload(), quality_payload())

        bad_v1 = v1_payload()
        bad_v1["evidence_identity"]["notes"] = "unexpected"
        with self.assertRaisesRegex(bundle.ShareBundleError, "evidence_identity unexpected fields"):
            bundle.validate_summaries(e2e_payload(), bad_v1, quality_payload())

    def test_all_three_summaries_must_be_passing(self):
        bad_e2e = e2e_payload()
        bad_e2e["answer_present"] = False
        with self.assertRaisesRegex(bundle.ShareBundleError, "answer was present"):
            bundle.validate_summaries(bad_e2e, v1_payload(), quality_payload())

        bad_status = e2e_payload()
        bad_status["status"] = "routed"
        with self.assertRaisesRegex(bundle.ShareBundleError, "status=answered"):
            bundle.validate_summaries(bad_status, v1_payload(), quality_payload())

        bad_v1 = v1_payload()
        bad_v1["v1_gate_passed"] = False
        with self.assertRaisesRegex(bundle.ShareBundleError, "v1_gate_passed=true"):
            bundle.validate_summaries(e2e_payload(), bad_v1, quality_payload())

        bad_quality = quality_payload()
        bad_quality["quality_evidence_complete"] = False
        with self.assertRaisesRegex(bundle.ShareBundleError, "quality_evidence_complete=true"):
            bundle.validate_summaries(e2e_payload(), v1_payload(), bad_quality)

    def test_canonical_gate_semantics_cannot_be_weakened(self):
        bad_latency = e2e_payload()
        bad_latency["latency_ms"] = 15001
        with self.assertRaisesRegex(bundle.ShareBundleError, "latency_ms"):
            bundle.validate_summaries(bad_latency, v1_payload(), quality_payload())

        lowered = v1_payload()
        lowered["requirements"]["mouth_raise_trials"] = 1
        with self.assertRaisesRegex(bundle.ShareBundleError, "exactly 30"):
            bundle.validate_summaries(e2e_payload(), lowered, quality_payload())

        weak_rate = v1_payload()
        weak_rate["results"]["mouth_raise_detected"] = 26
        weak_rate["results"]["detection_rate"] = round(26 / 30, 6)
        with self.assertRaisesRegex(bundle.ShareBundleError, "detection rate"):
            bundle.validate_summaries(e2e_payload(), weak_rate, quality_payload())

        bad_remaining = v1_payload()
        bad_remaining["remaining"]["non_trigger_trials"] = 1
        with self.assertRaisesRegex(bundle.ShareBundleError, "remainder must be zero"):
            bundle.validate_summaries(e2e_payload(), bad_remaining, quality_payload())

    def test_v1_rates_must_match_observed_counts(self):
        bad_detection = v1_payload()
        bad_detection["results"]["mouth_raise_detected"] = 27
        bad_detection["results"]["detection_rate"] = 1.0
        with self.assertRaisesRegex(bundle.ShareBundleError, "detection_rate is inconsistent"):
            bundle.validate_summaries(e2e_payload(), bad_detection, quality_payload())

        bad_false_rate = v1_payload()
        bad_false_rate["results"]["false_triggers"] = 5
        bad_false_rate["results"]["false_trigger_rate"] = 0.0
        with self.assertRaisesRegex(bundle.ShareBundleError, "false_trigger_rate is inconsistent"):
            bundle.validate_summaries(e2e_payload(), bad_false_rate, quality_payload())

        impossible = v1_payload()
        impossible["results"]["mouth_raise_detected"] = 31
        with self.assertRaisesRegex(bundle.ShareBundleError, "cannot exceed"):
            bundle.validate_summaries(e2e_payload(), impossible, quality_payload())

    def test_boolean_aliases_cannot_satisfy_numeric_gate_fields(self):
        bad_requirement = v1_payload()
        bad_requirement["requirements"]["mouth_raise_trials"] = True
        with self.assertRaisesRegex(bundle.ShareBundleError, "requirement must be an integer"):
            bundle.validate_summaries(e2e_payload(), bad_requirement, quality_payload())

        bad_remaining = v1_payload()
        bad_remaining["remaining"]["mouth_raise_trials"] = False
        with self.assertRaisesRegex(bundle.ShareBundleError, "remainder must be an integer"):
            bundle.validate_summaries(e2e_payload(), bad_remaining, quality_payload())

    def test_shareable_string_and_digest_fields_are_canonical(self):
        bad_version = e2e_payload()
        bad_version["app_version"] = "release-secret-text"
        with self.assertRaisesRegex(bundle.ShareBundleError, "MAJOR.MINOR.PATCH"):
            bundle.validate_summaries(bad_version, v1_payload(), quality_payload())

        bad_timestamp = e2e_payload()
        bad_timestamp["recorded_at_utc"] = "token-like-arbitrary-text"
        with self.assertRaisesRegex(bundle.ShareBundleError, "canonical UTC timestamp"):
            bundle.validate_summaries(bad_timestamp, v1_payload(), quality_payload())

        bad_config = v1_payload()
        bad_config["evidence_identity"]["detector_config"] = "v1\nsecret"
        with self.assertRaisesRegex(bundle.ShareBundleError, "printable comma-free"):
            bundle.validate_summaries(e2e_payload(), bad_config, quality_payload())

        bad_apk = quality_payload()
        bad_apk["apk_sha256"] = "not-a-digest"
        with self.assertRaisesRegex(bundle.ShareBundleError, "64-character hexadecimal"):
            bundle.validate_summaries(e2e_payload(), v1_payload(), bad_apk)

    def test_non_frozen_carrier_identity_is_rejected(self):
        wrong_source = e2e_payload()
        wrong_source["source_revision"] = "a" * 40
        wrong_v1 = v1_payload()
        wrong_v1["evidence_identity"]["source_revision"] = "a" * 40
        wrong_quality = quality_payload()
        wrong_quality["source_revision"] = "a" * 40
        with self.assertRaisesRegex(bundle.ShareBundleError, "frozen v1.5.2 carrier"):
            bundle.validate_summaries(wrong_source, wrong_v1, wrong_quality)

        wrong_apk = quality_payload()
        wrong_apk["apk_sha256"] = "b" * 64
        with self.assertRaisesRegex(bundle.ShareBundleError, "apk_sha256 does not match frozen"):
            bundle.validate_summaries(e2e_payload(), v1_payload(), wrong_apk)

        wrong_config = v1_payload()
        wrong_config["evidence_identity"]["detector_config"] = "raise-detector-v1;similarity=0.954"
        with self.assertRaisesRegex(bundle.ShareBundleError, "detector_config does not match"):
            bundle.validate_summaries(e2e_payload(), wrong_config, quality_payload())

    def test_cross_summary_identity_mismatch_is_rejected(self):
        bad_v1 = v1_payload()
        bad_v1["evidence_identity"]["source_revision"] = "b" * 40
        with self.assertRaisesRegex(bundle.ShareBundleError, "V1 source_revision"):
            bundle.validate_summaries(e2e_payload(), bad_v1, quality_payload())

    def test_symlink_output_parent_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            session = self.write_session(root)
            real_parent = root / "real-parent"
            real_parent.mkdir()
            linked_parent = root / "linked-parent"
            linked_parent.symlink_to(real_parent, target_is_directory=True)

            with self.assertRaisesRegex(bundle.ShareBundleError, "output parent must not be a symlink"):
                bundle.prepare_bundle(session, linked_parent / "share")
            self.assertFalse((real_parent / "share").exists())

    def test_existing_output_is_never_overwritten(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            session = self.write_session(root)
            output = root / "share"
            output.mkdir()
            marker = output / "keep.txt"
            marker.write_text("keep\n", encoding="utf-8")

            with self.assertRaisesRegex(bundle.ShareBundleError, "refusing to overwrite"):
                bundle.prepare_bundle(session, output)
            self.assertEqual(marker.read_text(encoding="utf-8"), "keep\n")

    def test_invalid_utf8_and_non_json_are_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            session = self.write_session(root)
            (session / "e2e-result.json").write_bytes(b"\xff")
            with self.assertRaisesRegex(bundle.ShareBundleError, "valid UTF-8"):
                bundle.prepare_bundle(session, root / "share")

        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            session = self.write_session(root)
            (session / "e2e-result.json").write_text("{not-json}\n", encoding="utf-8")
            with self.assertRaisesRegex(bundle.ShareBundleError, "valid JSON"):
                bundle.prepare_bundle(session, root / "share")


if __name__ == "__main__":
    unittest.main()
