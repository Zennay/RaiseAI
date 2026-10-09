import os
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "physical-validation.command"


class PhysicalValidationCliContractTest(unittest.TestCase):
    def run_cli(self, *args, env=None):
        process_env = os.environ.copy()
        if env:
            process_env.update(env)
        return subprocess.run(
            ["bash", str(CLI), *args],
            cwd=ROOT,
            env=process_env,
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

    def test_non_preparing_cli_paths_do_not_create_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / "home"
            home.mkdir()
            evidence = Path(tmp) / "evidence"
            env = {
                "HOME": str(home),
                "RAISE_EVIDENCE_ROOT": str(evidence),
            }

            cases = [
                (("help",), 0),
                (("not-a-command",), 2),
                (("status", "/does/not/exist"), 1),
                (("prepare", "/does/not/exist"), 1),
            ]
            for args, expected_code in cases:
                with self.subTest(args=args):
                    result = self.run_cli(*args, env=env)
                    self.assertEqual(expected_code, result.returncode, result.stdout)
                    self.assertFalse(
                        (home / ".raiseai").exists(),
                        "non-preparing CLI validation must not create ~/.raiseai",
                    )
                    self.assertFalse(
                        evidence.exists(),
                        "non-preparing CLI validation must not create evidence directories",
                    )


if __name__ == "__main__":
    unittest.main()
