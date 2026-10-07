import os
import subprocess
import tempfile
import textwrap
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "install-mac-adb-autoconnect.command"


class MacAdbAutoconnectContractTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.home = self.root / "home"
        self.bin = self.root / "bin"
        self.sdk = self.root / "sdk"
        self.home.mkdir()
        self.bin.mkdir()
        (self.sdk / "platform-tools").mkdir(parents=True)

        adb = self.sdk / "platform-tools" / "adb"
        adb.write_text("#!/bin/bash\nexit 0\n", encoding="utf-8")
        adb.chmod(0o755)

        uname = self.bin / "uname"
        uname.write_text(
            "#!/bin/bash\nprintf '%s\\n' \"${FAKE_UNAME:-Darwin}\"\n",
            encoding="utf-8",
        )
        uname.chmod(0o755)

        launchctl = self.bin / "launchctl"
        launchctl.write_text(
            textwrap.dedent(
                """#!/bin/bash
set -eu
printf '%s\n' "$*" >> "$LAUNCHCTL_LOG"
exit 0
"""
            ),
            encoding="utf-8",
        )
        launchctl.chmod(0o755)
        self.launchctl_log = self.root / "launchctl.log"

    def tearDown(self):
        self.temp.cleanup()

    def run_script(self, *args, fake_uname="Darwin"):
        env = os.environ.copy()
        env["HOME"] = str(self.home)
        env["ANDROID_SDK_ROOT"] = str(self.sdk)
        env["PATH"] = f"{self.bin}:{env['PATH']}"
        env["FAKE_UNAME"] = fake_uname
        env["LAUNCHCTL_LOG"] = str(self.launchctl_log)
        return subprocess.run(
            ["bash", str(SCRIPT), *args],
            cwd=ROOT,
            env=env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )

    def test_rejects_unknown_argument_before_platform_or_state_side_effects(self):
        result = self.run_script("--bogus", fake_uname="Linux")

        self.assertEqual(result.returncode, 2, result.stdout)
        self.assertIn("Usage:", result.stdout)
        self.assertFalse((self.home / ".raiseai").exists())
        self.assertFalse((self.home / "Library").exists())
        self.assertFalse(self.launchctl_log.exists())

    def test_rejects_extra_argument(self):
        result = self.run_script("--quiet", "extra")

        self.assertEqual(result.returncode, 2, result.stdout)
        self.assertIn("Usage:", result.stdout)
        self.assertFalse((self.home / ".raiseai").exists())

    def test_non_macos_noop_keeps_existing_contract(self):
        result = self.run_script(fake_uname="Linux")

        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertEqual(result.stdout.strip(), "macOS only.")
        self.assertFalse((self.home / ".raiseai").exists())

    def test_quiet_non_macos_noop_is_silent(self):
        result = self.run_script("--quiet", fake_uname="Linux")

        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertEqual(result.stdout, "")
        self.assertFalse((self.home / ".raiseai").exists())

    def test_darwin_install_creates_expected_contract_and_branding(self):
        result = self.run_script()

        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("Raise AI ADB auto-connect installed.", result.stdout)
        self.assertNotIn("Race AI", result.stdout)

        state = self.home / ".raiseai"
        helper = state / "bin" / "raiseai-adb-autoconnect"
        plist = self.home / "Library" / "LaunchAgents" / "nl.zennay.raiseai.adb-autoconnect.plist"
        marker = state / "autoconnect-installed"

        self.assertTrue(helper.is_file())
        self.assertTrue(os.access(helper, os.X_OK))
        helper_source = helper.read_text(encoding="utf-8")
        self.assertIn('awk \'NR>1 && $2=="device" {print $1}\'', helper_source)
        self.assertTrue(plist.is_file())
        self.assertTrue(marker.is_file())
        self.assertIn(str(helper), plist.read_text(encoding="utf-8"))
        self.assertTrue(self.launchctl_log.is_file())
        launchctl_calls = self.launchctl_log.read_text(encoding="utf-8")
        self.assertIn("bootstrap", launchctl_calls)
        self.assertIn("kickstart -k", launchctl_calls)

    def test_quiet_darwin_install_suppresses_success_copy(self):
        result = self.run_script("--quiet")

        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertEqual(result.stdout, "")
        self.assertTrue((self.home / ".raiseai" / "autoconnect-installed").is_file())


if __name__ == "__main__":
    unittest.main()
