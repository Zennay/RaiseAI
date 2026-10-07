from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
import importlib.util
from pathlib import Path
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "tools" / "run_python_contracts.py"

SPEC = importlib.util.spec_from_file_location("raise_python_contract_runner", RUNNER)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("could not load aggregate Python contract runner")
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class PythonContractRunnerTests(unittest.TestCase):
    def run_temporary_suite(self, source: str, filename: str) -> tuple[int, str]:
        with tempfile.TemporaryDirectory() as tmp:
            tests_dir = Path(tmp)
            (tests_dir / "__init__.py").write_text("", encoding="utf-8")
            (tests_dir / filename).write_text(source, encoding="utf-8")
            previous = MODULE.TESTS_DIR
            MODULE.TESTS_DIR = tests_dir
            output = StringIO()
            try:
                with redirect_stdout(output), redirect_stderr(output):
                    exit_code = MODULE.main()
            finally:
                MODULE.TESTS_DIR = previous
            return exit_code, output.getvalue()

    def test_passing_suite_returns_zero(self):
        exit_code, output = self.run_temporary_suite(
            """
import unittest

class PassingContract(unittest.TestCase):
    def test_passes(self):
        self.assertTrue(True)
""",
            "test_runner_pass_case.py",
        )
        self.assertEqual(exit_code, 0)
        self.assertNotIn("SKIPPED:", output)

    def test_failing_suite_returns_nonzero(self):
        exit_code, _ = self.run_temporary_suite(
            """
import unittest

class FailingContract(unittest.TestCase):
    def test_fails(self):
        self.fail("synthetic failure")
""",
            "test_runner_fail_case.py",
        )
        self.assertEqual(exit_code, 1)

    def test_skipped_suite_returns_nonzero_and_reports_test_identity(self):
        exit_code, output = self.run_temporary_suite(
            """
import unittest

class SkippedContract(unittest.TestCase):
    @unittest.skip("synthetic unsupported capability")
    def test_must_not_be_silently_skipped(self):
        pass
""",
            "test_runner_skip_case.py",
        )
        self.assertEqual(exit_code, 1)
        self.assertIn("aggregate Python contracts skipped 1 test(s)", output)
        self.assertIn(
            "test_must_not_be_silently_skipped",
            output,
        )
        self.assertIn("synthetic unsupported capability", output)


if __name__ == "__main__":
    unittest.main()
