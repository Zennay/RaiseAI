#!/usr/bin/env python3
"""Deterministic, hardware-free Raise AI phone/Watch identity parity tests."""
import importlib.util
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest import mock

SOURCE = Path(__file__).resolve().parents[1] / "tools" / "verify_phone_watch_datalayer_identity.py"
spec = importlib.util.spec_from_file_location("datalayer", SOURCE)
datalayer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(datalayer)

SIGNER_A = "ab" * 32
SIGNER_B = "cd" * 32
PACKAGE = "package: name='nl.zennay.raiseai' versionCode='1' versionName='0.1.0'"
CERT = "Signer #1 certificate SHA-256 digest: " + SIGNER_A
WATCH_PACKAGE = PACKAGE + "\\nuses-feature: name=\u0027android.hardware.type.watch\u0027"


class IdentityPreflightTests(unittest.TestCase):
    def test_valid_identity_metadata_is_accepted(self):
        self.assertEqual(datalayer.package_name(PACKAGE), datalayer.EXPECTED_PACKAGE)
        self.assertEqual(datalayer.signer_digest(CERT), SIGNER_A)

    def test_wrong_app_package_fails_before_pairing(self):
        with self.assertRaises(datalayer.CompatibilityError):
            datalayer.package_name(PACKAGE.replace("nl.zennay.raiseai", "com.attacker"))

    def test_missing_or_ambiguous_package_line_fails_closed(self):
        for output in ("", PACKAGE + "\n" + PACKAGE):
            with self.subTest(output=output), self.assertRaises(datalayer.CompatibilityError):
                datalayer.package_name(output)

    def test_multi_signer_certificates_fail_closed(self):
        for output in ("", CERT + "\nSigner #2 certificate SHA-256 digest: " + SIGNER_B):
            with self.subTest(output=output), self.assertRaises(datalayer.CompatibilityError):
                datalayer.signer_digest(output)

    def test_malformed_signer_or_digest_fails_closed(self):
        for output in ("Signer #1 certificate SHA-256 digest: no-hash", 
                       "Signer #1 certificate SHA-256 digest: " + SIGNER_A + "extra"):
            with self.subTest(output=output), self.assertRaises(datalayer.CompatibilityError):
                datalayer.signer_digest(output)

    def test_separated_digest_bytes_supported(self):
        digest = ":".join(SIGNER_A[x:x+2] for x in range(0,64,2))
        self.assertEqual(datalayer.signer_digest(
            "Signer #1 certificate SHA-256 digest: " + digest), SIGNER_A)

    def test_apk_missing_symlink_and_empty_are_refused(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "phone.apk"
            with self.assertRaises(datalayer.CompatibilityError):
                datalayer.checked_apk(p)
            p.touch()
            with self.assertRaises(datalayer.CompatibilityError):
                datalayer.checked_apk(p)
            p.write_bytes(b"apk")
            link = Path(d) / "alias.apk"
            link.symlink_to(p)
            with self.assertRaises(datalayer.CompatibilityError):
                datalayer.checked_apk(link)
            self.assertEqual(datalayer.checked_apk(p), p)

    def test_tool_error_and_missing_command_fail_without_exposing_stdout(self):
        with mock.patch.object(datalayer.shutil, "which", return_value=None):
            with self.assertRaises(datalayer.CompatibilityError):
                datalayer.checked_command("aapt", [])
        with mock.patch.object(datalayer.shutil, "which", return_value="/bin/aapt"), \
             mock.patch.object(datalayer.subprocess, "run",
                               return_value=subprocess.CompletedProcess([], 1, "secret", "secret")):
            with self.assertRaises(datalayer.CompatibilityError) as exc:
                datalayer.checked_command("aapt", [])
        self.assertNotIn("secret", str(exc.exception))

    def test_matching_fingerprint_allows_readonly_preflight(self):
        with tempfile.TemporaryDirectory() as d:
            phone, watch = Path(d)/"phone.apk", Path(d)/"watch.apk"
            phone.write_bytes(b"phone")
            watch.write_bytes(b"watch")
            with mock.patch.object(datalayer, "checked_command", side_effect=[
                PACKAGE, CERT, WATCH_PACKAGE, CERT
            ]) as calls:
                datalayer.preflight(phone, watch, "aapt", "apksigner")
            self.assertEqual(calls.call_count, 4)

    def test_different_watch_signer_is_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            phone, watch = Path(d)/"phone.apk", Path(d)/"watch.apk"
            phone.write_bytes(b"phone")
            watch.write_bytes(b"watch")
            with mock.patch.object(datalayer, "checked_command", side_effect=[
                PACKAGE, CERT, WATCH_PACKAGE, "Signer #1 certificate SHA-256 digest: " + SIGNER_B
            ]):
                with self.assertRaises(datalayer.CompatibilityError):
                    datalayer.preflight(phone, watch, "aapt", "apksigner")

    def test_two_phone_apks_cannot_be_mistaken_for_watch_pair(self):
        with tempfile.TemporaryDirectory() as d:
            phone, fake_watch = Path(d)/"phone.apk", Path(d)/"fake-watch.apk"
            phone.write_bytes(b"phone")
            fake_watch.write_bytes(b"phone copy")
            with mock.patch.object(datalayer, "checked_command", side_effect=[PACKAGE, CERT, PACKAGE, CERT]):
                with self.assertRaisesRegex(datalayer.CompatibilityError, "device roles"):
                    datalayer.preflight(phone, fake_watch, "aapt", "apksigner")

    def test_same_apk_path_is_not_two_device_identity_evidence(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)/"both.apk"
            p.write_bytes(b"fake")
            with mock.patch.object(datalayer, "checked_command") as calls:
                with self.assertRaises(datalayer.CompatibilityError):
                    datalayer.preflight(p, p, "aapt", "apksigner")
                calls.assert_not_called()


if __name__ == "__main__":
    unittest.main()
