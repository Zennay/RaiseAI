#!/usr/bin/env python3
"""Hardware-free security/negative tests for opt-in Android APK signer attestation."""
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("phone_signing_probe", ROOT / "tools" / "probe_official_chatgpt_phone.py")
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)

KNOWN_DIGEST = "a1" * 32
SPOOFED_DIGEST = "b2" * 32
BASE_PATH = "/data/app/~~identity/com.openai.chatgpt-123/base.apk"


class OfficialPhoneSignatureTests(unittest.TestCase):
    def test_base_apk_selected_from_normal_split_package(self):
        paths = "package:/data/app/~~identity/com.openai.chatgpt-123/split_config.apk\npackage:" + BASE_PATH
        self.assertEqual(probe.base_apk_path(paths), BASE_PATH)

    def test_duplicate_base_apk_is_ambiguous(self):
        with self.assertRaises(probe.ProbeError):
            probe.base_apk_path("package:" + BASE_PATH + "\npackage:" + BASE_PATH)

    def test_malformed_or_escape_path_is_refused(self):
        for path in ("/data/app/../shared/base.apk", "/tmp/base.apk", "/data/app/x/base.apk\r",
                     "/data/app/x/\u00e9/base.apk", "/data/app/x/a;b/base.apk"):
            with self.subTest(path=path), self.assertRaises(probe.ProbeError):
                probe.base_apk_path("package:" + path)

    def test_signer_parser_requires_exact_single_certificate(self):
        self.assertEqual(probe.extract_apksigner_sha256(
            "Verified using v2 scheme (APK Signature Scheme v2): true\n"
            "Signer #1 certificate SHA-256 digest: " + KNOWN_DIGEST + "\n"), KNOWN_DIGEST)
        self.assertEqual(probe.extract_apksigner_sha256(
            "Signer #1 certificate SHA-256 digest: " + ":".join([KNOWN_DIGEST[x:x+2] for x in range(0,64,2)])),
            KNOWN_DIGEST)
        for text in ("", "Signer #1 certificate SHA-256 digest: not-a-hash",
                     "Signer #1 certificate SHA-256 digest: " + KNOWN_DIGEST + "\n"
                     "Signer #2 certificate SHA-256 digest: " + KNOWN_DIGEST):
            with self.subTest(text=text), self.assertRaises(probe.ProbeError):
                probe.extract_apksigner_sha256(text)

    def _fake_run(self, args, **kwargs):
        if "pull" in args:
            Path(args[-1]).write_bytes(b"apk")
            return subprocess.CompletedProcess(args, 0, stdout="pulled", stderr="")
        return subprocess.CompletedProcess(
            args, 0, stdout="Signer #1 certificate SHA-256 digest: " + KNOWN_DIGEST, stderr=""
        )

    def _verify(self, expected=KNOWN_DIGEST, run=None, size="3"):
        with mock.patch.object(probe.shutil, "which", return_value="/sdk/apksigner"), \
             mock.patch.object(probe, "adb_call", side_effect=["package:" + BASE_PATH, size]), \
             mock.patch.object(probe.subprocess, "run", side_effect=run or self._fake_run) as exec_mock:
            probe.verify_signing_certificate("adb", "phone", expected)
        return exec_mock

    def test_verifies_exact_expected_signing_certificate(self):
        runner = self._verify()
        self.assertEqual(runner.call_count, 2)
        self.assertEqual(runner.call_args_list[1].args[0][:3],
                         ["apksigner", "verify", "--print-certs"])

    def test_refuses_tampered_or_unknown_certificate(self):
        with self.assertRaisesRegex(probe.ProbeError, "does not match"):
            self._verify(SPOOFED_DIGEST)

    def test_bad_expected_digest_refused_before_device_access(self):
        with mock.patch.object(probe, "adb_call") as adb:
            with self.assertRaises(probe.ProbeError):
                probe.verify_signing_certificate("adb", "phone", "not-a-sha")
            adb.assert_not_called()

    def test_missing_apksigner_fails_closed_before_adb_pull(self):
        with mock.patch.object(probe.shutil, "which", return_value=None), \
             mock.patch.object(probe, "adb_call") as adb:
            with self.assertRaises(probe.ProbeError):
                probe.verify_signing_certificate("adb", "phone", KNOWN_DIGEST)
            adb.assert_not_called()

    def test_unbounded_apk_rejected_before_pull(self):
        with mock.patch.object(probe.shutil, "which", return_value="/sdk/apksigner"), \
             mock.patch.object(probe, "adb_call",
                               side_effect=["package:" + BASE_PATH, str(probe.MAX_BASE_APK_BYTES + 1)]), \
             mock.patch.object(probe.subprocess, "run") as subprocess_run:
            with self.assertRaises(probe.ProbeError):
                probe.verify_signing_certificate("adb", "phone", KNOWN_DIGEST)
            subprocess_run.assert_not_called()

    def test_corrupt_or_failing_apksigner_cannot_attest(self):
        def fail_apksigner(args, **kwargs):
            if "pull" in args:
                Path(args[-1]).write_bytes(b"apk")
                return subprocess.CompletedProcess(args, 0, "", "")
            return subprocess.CompletedProcess(args, 1, "", "untrusted apk")
        with self.assertRaises(probe.ProbeError):
            self._verify(run=fail_apksigner)

    def test_missing_downloaded_apk_is_rejected(self):
        with self.assertRaises(probe.ProbeError):
            self._verify(run=lambda args, **kwargs: subprocess.CompletedProcess(args, 0, "", ""))

    def test_signature_mismatch_never_launches_or_records_success(self):
        with mock.patch.object(probe.shutil, "which", return_value="/bin/adb"), \
             mock.patch.object(probe, "select_serial", return_value="phone"), \
             mock.patch.object(probe, "inspect_phone",
                               return_value={"model": "Android phone", "chatgpt_package": probe.OFFICIAL_PACKAGE}), \
             mock.patch.object(probe, "verify_signing_certificate", side_effect=probe.ProbeError("bad signer")), \
             mock.patch.object(probe, "launch_official_app") as launcher, \
             contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(probe.main(["--launch", "--expected-signer-sha256", KNOWN_DIGEST]), 2)
            launcher.assert_not_called()

    def test_explicit_good_reference_records_truthful_phone_only_evidence(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "result.json"
            with mock.patch.object(probe.shutil, "which", return_value="/bin/adb"), \
                 mock.patch.object(probe, "select_serial", return_value="private-phone"), \
                 mock.patch.object(probe, "inspect_phone",
                                   return_value={"model": "Android phone", "chatgpt_package": probe.OFFICIAL_PACKAGE}), \
                 mock.patch.object(probe, "verify_signing_certificate") as verifier, \
                 mock.patch.object(probe, "launch_official_app", return_value=150.0), \
                 contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(probe.main(["--launch", "--expected-signer-sha256", KNOWN_DIGEST,
                                             "--evidence", str(path)]), 0)
                verifier.assert_called_once()
            evidence = json.loads(path.read_text())
            self.assertTrue(evidence["publisher_signature_verified"])
            self.assertFalse(evidence["watch_microphone_bridge_verified"])
            self.assertFalse(evidence["watch_speaker_bridge_verified"])
            self.assertFalse(evidence["consumer_voice_api_claimed"])
            self.assertNotIn("private-phone", path.read_text())

    def test_invalid_cli_digest_is_rejected_before_adb(self):
        with contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as ctx:
                probe.main(["--expected-signer-sha256", "invalid"])
        self.assertEqual(ctx.exception.code, 2)


if __name__ == "__main__":
    unittest.main()
