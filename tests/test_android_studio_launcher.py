import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LAUNCHER = ROOT / "open-in-android-studio.command"


class AndroidStudioLauncherContractTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = LAUNCHER.read_text(encoding="utf-8")

    def run_launcher(self, *args):
        return subprocess.run(
            [str(LAUNCHER), *args],
            cwd=ROOT,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=5,
        )

    def test_shell_contract_is_strict_and_repository_relative(self):
        lines = self.source.splitlines()
        self.assertEqual(lines[0], "#!/bin/bash")
        self.assertEqual(lines[1], "set -euo pipefail")
        self.assertIn('SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd -P)"', self.source)
        self.assertIn('cd "$SCRIPT_DIR"', self.source)

    def test_unexpected_arguments_fail_closed_before_launch(self):
        result = self.run_launcher("unexpected")
        self.assertEqual(result.returncode, 2, result.stdout)
        self.assertIn("Usage: ./open-in-android-studio.command", result.stdout)

    def test_missing_android_studio_is_nonzero_and_noninteractive_safe(self):
        if Path("/Applications/Android Studio.app").is_dir():
            self.skipTest("Android Studio exists on this runner")
        result = self.run_launcher()
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("Android Studio was not found", result.stdout)

    def test_success_path_propagates_open_exit_status(self):
        self.assertIn('exec open -a "Android Studio" "$SCRIPT_DIR"', self.source)
        self.assertNotIn('open -a "Android Studio" "$PWD"', self.source)


if __name__ == "__main__":
    unittest.main()
