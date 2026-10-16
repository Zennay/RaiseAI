#!/usr/bin/env python3
"""Deterministic, hardware-free contract tests for official-app phone probing."""
import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import stat
import subprocess
import tempfile
import unittest
from unittest import mock

SOURCE = Path(__file__).resolve().parents[1] / "tools" / "probe_official_chatgpt_phone.py"
spec = importlib.util.spec_from_file_location("phone_probe", SOURCE)
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)


class PhoneProbeTests(unittest.TestCase):
    def test_one_authorised_device(self):
        with mock.patch.object(probe, "adb_call", return_value="List of devices attached\nphone123\tdevice\n"):
            self.assertEqual(probe.select_serial("adb", None), "phone123")

    def test_multiple_devices_require_selection(self):
        devices = "List of devices attached\nphone1\tdevice\nphone2\tdevice\n"
        with mock.patch.object(probe, "adb_call", return_value=devices):
            with self.assertRaises(probe.ProbeError):
                probe.select_serial("adb", None)
            self.assertEqual(probe.select_serial("adb", "phone2"), "phone2")

    def test_offline_or_unauthorised_device_refused(self):
        devices = "List of devices attached\np1\tunauthorized\np2\toffline\n"
        with mock.patch.object(probe, "adb_call", return_value=devices):
            with self.assertRaises(probe.ProbeError):
                probe.select_serial("adb", None)

    def test_injection_in_serial_refused(self):
        with mock.patch.object(probe, "adb_call", return_value="List of devices attached\nphone\tdevice\n"):
            with self.assertRaises(probe.ProbeError):
                probe.select_serial("adb", "phone;rm -rf /")

    def test_only_real_phones_accepted(self):
        with mock.patch.object(probe, "adb_call", return_value="true"):
            with self.assertRaises(probe.ProbeError):
                probe.inspect_phone("adb", "phone")

    def test_unverifiable_device_type_rejected(self):
        with mock.patch.object(probe, "adb_call", return_value=""):
            with self.assertRaises(probe.ProbeError):
                probe.inspect_phone("adb", "phone")

    def test_no_official_app_fails_closed(self):
        with mock.patch.object(probe, "adb_call", side_effect=["false", ""]):
            with self.assertRaises(probe.ProbeError):
                probe.inspect_phone("adb", "phone")

    def test_installed_official_app_phone(self):
        with mock.patch.object(probe, "adb_call", side_effect=["false", "package:/data/app/base.apk", "Pixel 8"]):
            self.assertEqual(probe.inspect_phone("adb", "phone")["chatgpt_package"], "com.openai.chatgpt")

    def test_launcher_uses_no_deep_links_or_private_activities(self):
        with mock.patch.object(probe, "adb_call", return_value="Starting: Intent { act=android.intent.action.MAIN pkg=com.openai.chatgpt }") as f:
            with mock.patch.object(probe.time, "monotonic", side_effect=[10.0, 10.25]):
                self.assertEqual(probe.launch_official_app("adb", "phone"), 250.0)
        args = f.call_args.args[1]
        self.assertEqual(args, ["-s", "phone", "shell", "am", "start",
                                "-a", "android.intent.action.MAIN",
                                "-c", "android.intent.category.LAUNCHER",
                                "-p", "com.openai.chatgpt"])
        self.assertNotIn("VOICE", " ".join(args))
        self.assertNotIn("monkey", args)

    def test_launcher_requires_actual_injected_event(self):
        with mock.patch.object(probe, "adb_call", return_value="Error: Activity not started"):
            with self.assertRaises(probe.ProbeError):
                probe.launch_official_app("adb", "phone")

    def test_existing_foreground_app_is_ok(self):
        with mock.patch.object(probe, "adb_call", return_value="Warning: Activity not started, its current task has been brought to the front"):
            with mock.patch.object(probe.time, "monotonic", side_effect=[1.0, 1.01]):
                self.assertEqual(probe.launch_official_app("adb", "phone"), 10.0)

    def test_blank_launcher_response_is_not_success(self):
        with mock.patch.object(probe, "adb_call", return_value=""):
            with self.assertRaises(probe.ProbeError):
                probe.launch_official_app("adb", "phone")

    def test_adb_nonzero_failure_omits_sensitive_stderr(self):
        fake = subprocess.CompletedProcess([], 1, stdout="", stderr="sensitive device log")
        with mock.patch.object(probe.subprocess, "run", return_value=fake):
            with self.assertRaises(probe.ProbeError) as ctx:
                probe.adb_call("adb", ["devices"])
        self.assertNotIn("sensitive device log", str(ctx.exception))

    def test_adb_timeout_is_fail_closed(self):
        with mock.patch.object(probe.subprocess, "run", side_effect=subprocess.TimeoutExpired("adb", 3)):
            with self.assertRaises(probe.ProbeError):
                probe.adb_call("adb", ["devices"])

    def test_write_private_new_only_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "measurements.json"
            probe.evidence_write(target, {"watch_speaker_bridge_verified": False})
            self.assertEqual(json.loads(target.read_text())["watch_speaker_bridge_verified"], False)
            if os.name == "posix":
                self.assertEqual(stat.S_IMODE(target.stat().st_mode), 0o600)
            with self.assertRaises(FileExistsError):
                probe.evidence_write(target, {"fake": True})

    def test_symlink_evidence_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "real.json"
            target.write_text("original")
            linked = Path(tmp) / "alias.json"
            linked.symlink_to(target)
            with self.assertRaises(OSError):
                probe.evidence_write(linked, {"new": "data"})
            self.assertEqual(target.read_text(), "original")

    def test_check_only_does_not_launch_app(self):
        with mock.patch.object(probe.shutil, "which", return_value="/bin/adb"), \
             mock.patch.object(probe, "select_serial", return_value="phone"), \
             mock.patch.object(probe, "inspect_phone", return_value={"model": "Pixel 8", "chatgpt_package": "com.openai.chatgpt"}), \
             mock.patch.object(probe, "launch_official_app") as launcher:
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                self.assertEqual(probe.main([]), 0)
        launcher.assert_not_called()
        self.assertIn("package name alone is NOT authenticity proof", output.getvalue())
        self.assertIn("NOT PROVEN: official app signing", output.getvalue())

    def test_interactive_requires_launch(self):
        with contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as ctx:
                probe.main(["--interactive"])
        self.assertEqual(ctx.exception.code, 2)

    def test_evidence_schema_never_claims_watch_audio(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "voice.json"
            with mock.patch.object(probe.shutil, "which", return_value="/bin/adb"), \
                 mock.patch.object(probe, "select_serial", return_value="private-serial"), \
                 mock.patch.object(probe, "inspect_phone", return_value={"model": "Pixel 8", "chatgpt_package": "com.openai.chatgpt"}), \
                 mock.patch.object(probe, "launch_official_app", return_value=145.2), \
                 contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(probe.main(["--launch", "--evidence", str(target)]), 0)
            evidence = json.loads(target.read_text())
            self.assertFalse(evidence["watch_microphone_bridge_verified"])
            self.assertFalse(evidence["watch_speaker_bridge_verified"])
            self.assertFalse(evidence["consumer_voice_api_claimed"])
            self.assertEqual(evidence["launch_command_ms"], 145.2)
            self.assertNotIn("private-serial", target.read_text())


if __name__ == "__main__":
    unittest.main()
