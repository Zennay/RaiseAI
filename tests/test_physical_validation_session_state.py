import json
import os
import pathlib
import subprocess
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]


def session_payload():
    return {
        "schema_version": 1,
        "started_at_utc": "2026-10-06T09:00:00Z",
        "app_version": "1.5.2",
        "source_revision": "a" * 40,
        "watch_model": "SM_L315F",
        "watch_serial": "watch-1",
        "install_mode": "prebuilt_apk",
        "apk_sha256": "b" * 64,
        "installed_apk_sha256": "b" * 64,
        "e2e_passed": False,
        "v1_gate_passed": False,
    }


class PhysicalValidationSessionStateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.base = pathlib.Path(self.temp.name)
        self.home = self.base / "home"
        self.state = self.home / ".raiseai"
        self.evidence = self.state / "evidence"
        self.session = self.evidence / "session-a"
        self.session.mkdir(parents=True)
        (self.session / "session.json").write_text(
            json.dumps(session_payload(), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        self.env = os.environ.copy()
        self.env["HOME"] = str(self.home)
        self.env["RAISE_EVIDENCE_ROOT"] = str(self.evidence)

    def tearDown(self):
        self.temp.cleanup()

    def run_validation(self, *args):
        return subprocess.run(
            ["bash", str(ROOT / "physical-validation.command"), *args],
            cwd=ROOT,
            env=self.env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )

    def publish_pointer(self):
        completed = subprocess.run(
            [
                "python3",
                str(ROOT / "tools" / "physical-session-pointer.py"),
                "publish",
                str(self.state / "latest-physical-validation-session"),
                str(self.session),
                str(self.evidence),
            ],
            cwd=ROOT,
            env=self.env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stdout)

    def test_status_resolves_atomically_published_latest_session(self):
        self.publish_pointer()
        completed = self.run_validation("status")
        self.assertEqual(completed.returncode, 0, completed.stdout)
        self.assertIn('"watch_serial": "watch-1"', completed.stdout)
        self.assertIn('"schema_version": 1', completed.stdout)

    def test_status_fails_closed_on_corrupt_latest_pointer(self):
        self.state.mkdir(parents=True, exist_ok=True)
        pointer = self.state / "latest-physical-validation-session"
        pointer.write_text("relative/session\n", encoding="utf-8")
        completed = self.run_validation("status")
        self.assertNotEqual(completed.returncode, 0)
        self.assertIn("latest-session pointer must contain an absolute path", completed.stdout)
        self.assertIn("No valid previous physical validation session found.", completed.stdout)

    def test_verify_e2e_rejects_existing_result_before_diagnostics_pull(self):
        (self.session / "e2e-result.json").write_text(
            '{"valid":true}\n',
            encoding="utf-8",
        )
        completed = self.run_validation("verify-e2e", str(self.session))
        self.assertNotEqual(completed.returncode, 0)
        self.assertIn("Refusing to reuse physical validation result path", completed.stdout)
        self.assertEqual(list(self.session.glob("watch-diagnostics-*")), [])

    def test_verify_v1_rejects_existing_result_before_watch_data_pull(self):
        payload = session_payload()
        payload["e2e_passed"] = True
        payload["e2e_verified_at_utc"] = "2026-10-06T09:05:00Z"
        (self.session / "session.json").write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        (self.session / "v1-result.json").write_text(
            '{"v1_gate_passed":true}\n',
            encoding="utf-8",
        )
        completed = self.run_validation("verify-v1", str(self.session))
        self.assertNotEqual(completed.returncode, 0)
        self.assertIn("Refusing to reuse physical validation result path", completed.stdout)
        self.assertEqual(list(self.session.glob("watch-sensor-trials-*.csv")), [])

    def test_status_fails_closed_on_latest_pointer_symlink(self):
        self.state.mkdir(parents=True, exist_ok=True)
        target = self.base / "pointer-target"
        target.write_text(str(self.session.resolve()) + "\n", encoding="utf-8")
        (self.state / "latest-physical-validation-session").symlink_to(target)
        completed = self.run_validation("status")
        self.assertNotEqual(completed.returncode, 0)
        self.assertIn("refusing symlink latest-session pointer", completed.stdout)


if __name__ == "__main__":
    unittest.main()
