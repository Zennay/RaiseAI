import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LAUNCHER = ROOT / "start-physical-handoff.command"


class PhysicalHandoffLauncherCliTest(unittest.TestCase):
    def run_launcher(self, *args):
        return subprocess.run(
            ["bash", str(LAUNCHER), *args],
            cwd=ROOT,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=5,
        )

    def test_missing_argument_fails_before_artifact_inspection(self):
        result = self.run_launcher()
        self.assertEqual(result.returncode, 2, result.stdout)
        self.assertIn("Usage:", result.stdout)
        self.assertNotIn("Physical handoff must contain", result.stdout)

    def test_profile_mode_rejects_surplus_arguments_before_artifact_inspection(self):
        result = self.run_launcher("/tmp/profile", "unexpected")
        self.assertEqual(result.returncode, 2, result.stdout)
        self.assertIn("Usage:", result.stdout)
        self.assertNotIn("Physical handoff must contain", result.stdout)

    def test_verify_only_rejects_surplus_arguments_before_artifact_inspection(self):
        result = self.run_launcher("--verify-only", "unexpected")
        self.assertEqual(result.returncode, 2, result.stdout)
        self.assertIn("Usage:", result.stdout)
        self.assertNotIn("Physical handoff must contain", result.stdout)


if __name__ == "__main__":
    unittest.main()
