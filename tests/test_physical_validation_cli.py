import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "physical-validation.command"


class PhysicalValidationCliContractTest(unittest.TestCase):
    def run_cli(self, *args):
        return subprocess.run(
            [str(CLI), *args],
            cwd=ROOT,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=5,
        )

    def test_help_rejects_extra_arguments(self):
        result = self.run_cli("help", "unexpected")
        self.assertEqual(result.returncode, 2, result.stdout)
        self.assertIn("Too many arguments for help.", result.stdout)
        self.assertIn("Usage:", result.stdout)

    def test_status_rejects_extra_arguments_before_session_access(self):
        result = self.run_cli("status", "/does/not/exist", "unexpected")
        self.assertEqual(result.returncode, 2, result.stdout)
        self.assertIn("Too many arguments for status.", result.stdout)
        self.assertNotIn("Invalid session", result.stdout)

    def test_prepare_rejects_extra_arguments_before_side_effects(self):
        result = self.run_cli("prepare", "/does/not/exist", "unexpected")
        self.assertEqual(result.returncode, 2, result.stdout)
        self.assertIn("Too many arguments for prepare.", result.stdout)
        self.assertNotIn("Gateway profile not found", result.stdout)

    def test_unknown_command_stays_usage_error(self):
        result = self.run_cli("not-a-command")
        self.assertEqual(result.returncode, 2, result.stdout)
        self.assertIn("Unknown command: not-a-command", result.stdout)


if __name__ == "__main__":
    unittest.main()
