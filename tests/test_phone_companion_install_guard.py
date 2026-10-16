#!/usr/bin/env python3
"""Hardware-free fail-closed contract tests for the phone-only installer."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
INSTALLER = ROOT / "phone-companion" / "install-phone.command"


class PhoneCompanionInstallerSafetyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.dir = Path(self.temp.name)
        self.record = self.dir / "adb-install-calls.log"
        adb = self.dir / "adb"
        adb.write_text(
            "#!/usr/bin/env bash\n"
            "set -euo pipefail\n"
            "if [[ \"$1\" == devices ]]; then\n"
            "  printf 'List of devices attached\\n'\n"
            "  printf '%s\\t%s\\n' \"\${FAKE_SERIAL:-testphone}\" \"\${FAKE_DEVICE_STATE:-device}\"\n"
            "elif [[ \"$3\" == shell && \"$4\" == pm && \"$5\" == has-feature ]]; then\n"
            "  printf '%s\\n' \"\${FAKE_WATCH_STATE:-true}\"\n"
            "elif [[ \"$3\" == install ]]; then\n"
            "  printf 'INSTALL ATTEMPT\\n' >> \"\${FAKE_RECORD}\"\n"
            "  exit 1\n"
            "else\n"
            "  echo 'Unexpected ADB call' >&2\n"
            "  exit 90\n"
            "fi\n"
        )
        adb.chmod(0o755)

    def run_installer(self, *args, **updates):
        env = os.environ.copy()
        env.update({"PATH": str(self.dir) + os.pathsep + os.environ.get("PATH", ""),
                    "FAKE_RECORD": str(self.record)})
        env.update(updates)
        return subprocess.run(
            ["bash", str(INSTALLER), *args],
            capture_output=True, text=True, timeout=6, env=env
        )

    def assert_no_install(self):
        self.assertFalse(self.record.exists(), "Installer must never invoke adb install")

    def test_missing_phone_serial_refused(self):
        self.assertEqual(self.run_installer().returncode, 2)
        self.assert_no_install()

    def test_invalid_adb_serial_including_shell_metacharacters_refused(self):
        for serial in ("fake;echo", "watch$HOME", "../watch", "-s", "a"*129):
            with self.subTest(serial=serial):
                self.assertEqual(self.run_installer(serial).returncode, 2)
                self.assert_no_install()

    def test_not_authorized_target_refused(self):
        self.assertNotEqual(self.run_installer("testphone", FAKE_DEVICE_STATE="unauthorized").returncode, 0)
        self.assert_no_install()

    def test_offline_target_refused(self):
        self.assertNotEqual(self.run_installer("testphone", FAKE_DEVICE_STATE="offline").returncode, 0)
        self.assert_no_install()

    def test_wrong_target_refused(self):
        self.assertNotEqual(self.run_installer("other-phone").returncode, 0)
        self.assert_no_install()

    def test_wear_os_watch_is_never_install_target(self):
        out = self.run_installer("testphone", FAKE_WATCH_STATE="true")
        self.assertNotEqual(out.returncode, 0)
        self.assertIn("REFUSED", out.stderr)
        self.assert_no_install()

    def test_unverifiable_watch_feature_refused(self):
        self.assertNotEqual(self.run_installer("testphone", FAKE_WATCH_STATE="unknown").returncode, 0)
        self.assert_no_install()

    def test_extra_unrecognized_flags_refused(self):
        self.assertEqual(self.run_installer("testphone", "--unsafe-device").returncode, 2)
        self.assert_no_install()

    def test_authorized_phone_without_exact_built_apk_refused(self):
        # Tests must never create arbitrary build output in a checked-out repository.
        # A normal clean checkout has no built phone companion APK yet.
        out = self.run_installer("testphone", FAKE_WATCH_STATE="false")
        self.assertNotEqual(out.returncode, 0)
        self.assertIn("Expected exactly one", out.stderr)
        self.assert_no_install()


if __name__ == "__main__":
    unittest.main()
