"""Fail-closed tests for aggregate contract discovery root identity."""
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

RUNNER = Path(__file__).resolve().parents[1] / "tools" / "run_python_contracts.py"
spec = importlib.util.spec_from_file_location("raise_root_integrity_runner", RUNNER)
if spec is None or spec.loader is None:
    raise RuntimeError("contract runner unavailable")
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


class ContractRootIntegrityTests(unittest.TestCase):
    def evaluate(self, root: Path):
        output = StringIO()
        with patch.object(runner, "TESTS_DIR", root):
            with redirect_stdout(output), redirect_stderr(output):
                status = runner.run_contracts()
        return status, output.getvalue()

    def test_directory_symlink_is_rejected_before_import(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            real = base / "real"
            real.mkdir()
            (real / "test_untrusted.py").write_text(
                'raise RuntimeError("must never import")\n', encoding="utf-8"
            )
            alias = base / "tests"
            alias.symlink_to(real, target_is_directory=True)
            status, output = self.evaluate(alias)
            self.assertEqual(status, 1, output)
            self.assertIn("root must be a real directory", output)
            self.assertNotIn("must never import", output)

    def test_regular_file_root_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "tests"
            root.write_text("not a directory", encoding="utf-8")
            status, output = self.evaluate(root)
            self.assertEqual(status, 1, output)
            self.assertIn("root must be a real directory", output)

    def test_missing_root_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            status, output = self.evaluate(Path(tmp) / "missing")
            self.assertEqual(status, 1, output)
            self.assertIn("root inaccessible", output)

    def test_real_empty_directory_keeps_existing_zero_tests_guard(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "tests"
            root.mkdir()
            status, output = self.evaluate(root)
            self.assertEqual(status, 1, output)
            self.assertIn("discovery found zero tests", output)


if __name__ == "__main__":
    unittest.main()
