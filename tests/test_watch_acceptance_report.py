import importlib.util
import json
import pathlib
import tempfile
import unittest

MODULE_PATH = pathlib.Path(__file__).resolve().parents[1] / "tools" / "build-watch-acceptance-report.py"
SPEC = importlib.util.spec_from_file_location("watch_acceptance_report", MODULE_PATH)
reporter = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(reporter)

REVISION = "8f719bb273f9b997848864f342598e7df5f090e5"
APK_SHA = "a" * 64


def write_json(path, payload):
    path.write_text(json.dumps(payload), encoding="utf-8")


def make_session(root):
    write_json(
        root / "session.json",
        {
            "schema_version": 1,
            "app_version": "1.5.2",
            "source_revision": REVISION,
            "watch_model": "SM_L315F",
            "watch_serial": "watch-1",
            "install_mode": "prebuilt_apk",
            "apk_sha256": APK_SHA,
            "installed_apk_sha256": APK_SHA,
            "e2e_passed": True,
            "v1_gate_passed": True,
        },
    )
    write_json(
        root / "e2e-result.json",
        {
            "valid": True,
            "outcome": "success",
            "route": "quick_ai",
            "status": "ok",
            "latency_ms": 1250,
            "input_length_chars": 22,
            "answer_present": True,
            "execution_enabled": True,
            "recorded_at_utc": "2026-10-04T23:40:00Z",
            "app_version": "1.5.2",
            "source_revision": REVISION,
        },
    )
    write_json(
        root / "v1-result.json",
        {
            "schema_version": 1,
            "v1_gate_passed": True,
            "evidence_identity": {
                "app_version": "1.5.2",
                "source_revision": REVISION,
                "detector_config": "raise-detector-v1;similarity=0.955",
            },
            "requirements": {
                "mouth_raise_trials": 30,
                "non_trigger_trials": 100,
                "min_detection_rate": 0.90,
                "max_false_trigger_rate": 0.05,
            },
            "results": {
                "mouth_raise_trials": 30,
                "mouth_raise_detected": 28,
                "detection_rate": 0.933333,
                "non_trigger_trials": 100,
                "false_triggers": 3,
                "false_trigger_rate": 0.03,
            },
            "remaining": {"mouth_raise_trials": 0, "non_trigger_trials": 0},
            "rejected_trial_count": 2,
        },
    )


class WatchAcceptanceReportTests(unittest.TestCase):
    def test_builds_pass_report_for_consistent_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            make_session(root)
            report = reporter.build_report(root)
            self.assertTrue(report["acceptance_passed"])
            self.assertEqual(report["identity"]["source_revision"], REVISION)
            self.assertEqual(report["v1"]["detection_rate"], 0.933333)
            markdown = reporter.render_markdown(report)
            self.assertIn("**Result: PASS**", markdown)
            self.assertNotIn("transcript", json.dumps(report).lower())

    def test_rejects_mismatched_e2e_revision(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            make_session(root)
            e2e = json.loads((root / "e2e-result.json").read_text())
            e2e["source_revision"] = "b" * 40
            write_json(root / "e2e-result.json", e2e)
            with self.assertRaisesRegex(reporter.AcceptanceError, "E2E source_revision does not match"):
                reporter.build_report(root)

    def test_rejects_unpassed_session_gate(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            make_session(root)
            session = json.loads((root / "session.json").read_text())
            session["v1_gate_passed"] = False
            write_json(root / "session.json", session)
            with self.assertRaisesRegex(reporter.AcceptanceError, "V1 gate is not marked passed"):
                reporter.build_report(root)

    def test_rejects_weak_or_incomplete_v1_requirements(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            make_session(root)
            v1 = json.loads((root / "v1-result.json").read_text())
            v1["requirements"]["non_trigger_trials"] = 50
            write_json(root / "v1-result.json", v1)
            with self.assertRaisesRegex(reporter.AcceptanceError, "at least 100"):
                reporter.build_report(root)

    def test_rejects_installed_apk_mismatch(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            make_session(root)
            session = json.loads((root / "session.json").read_text())
            session["installed_apk_sha256"] = "b" * 64
            write_json(root / "session.json", session)
            with self.assertRaisesRegex(reporter.AcceptanceError, "does not match prepared APK"):
                reporter.build_report(root)


if __name__ == "__main__":
    unittest.main()
