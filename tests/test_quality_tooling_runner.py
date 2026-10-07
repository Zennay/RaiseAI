from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "tools" / "run_quality_tooling_contracts.py"
SPEC = importlib.util.spec_from_file_location("raise_quality_tooling_runner", RUNNER)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("could not load quality tooling contract runner")
runner = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(runner)


EXPECTED_MODULES = (
    "tests.test_adb_device_binding",
    "tests.test_all_workflow_action_pins",
    "tests.test_frozen_acceptance_launcher",
    "tests.test_frozen_physical_handoff_fetcher",
    "tests.test_physical_observation_template",
    "tests.test_physical_observation_validator",
    "tests.test_physical_validation_cli",
    "tests.test_quality_tooling_runner",
    "tests.test_quality_tooling_workflow",
    "tests.test_quality_workflow_action_pinning",
    "tests.test_source_text_review_integrity",
    "tests.test_watch_data_analyzer",
    "tests.test_watch_apk_identity",
    "tests.test_watch_e2e_evidence_validator",
    "tests.test_watch_sensor_trace_analyzer",
    "tests.test_watch_sensor_trial_analyzer",
)


class QualityToolingRunnerTests(unittest.TestCase):
    def test_allowlist_is_exact_ordered_and_duplicate_free(self):
        self.assertEqual(runner.QUALITY_MODULES, EXPECTED_MODULES)
        self.assertEqual(len(runner.QUALITY_MODULES), len(set(runner.QUALITY_MODULES)))

    def test_empty_allowlist_fails_closed(self):
        output = StringIO()
        with redirect_stdout(output), redirect_stderr(output):
            exit_code = runner.run_contracts(())
        self.assertEqual(exit_code, 1)
        self.assertIn("module allowlist is empty", output.getvalue())

    def test_duplicate_allowlist_fails_closed(self):
        output = StringIO()
        with redirect_stdout(output), redirect_stderr(output):
            exit_code = runner.run_contracts(("tests.test_quality_tooling_runner",) * 2)
        self.assertEqual(exit_code, 1)
        self.assertIn("allowlist contains duplicates", output.getvalue())

    def test_named_module_without_tests_fails_closed(self):
        with tempfile.TemporaryDirectory(prefix="raise-quality-empty-") as tmp:
            root = Path(tmp)
            package = root / "quality_fixture"
            package.mkdir()
            (package / "__init__.py").write_text("", encoding="utf-8")
            (package / "empty_contract.py").write_text("SENTINEL = True\n", encoding="utf-8")
            sys.path.insert(0, str(root))
            try:
                output = StringIO()
                with redirect_stdout(output), redirect_stderr(output):
                    exit_code = runner.run_contracts(("quality_fixture.empty_contract",))
            finally:
                sys.path.remove(str(root))
                sys.modules.pop("quality_fixture.empty_contract", None)
                sys.modules.pop("quality_fixture", None)

        self.assertEqual(exit_code, 1)
        self.assertIn(
            "EMPTY-QUALITY-MODULE: quality_fixture.empty_contract",
            output.getvalue(),
        )

    def test_import_failure_is_a_test_failure(self):
        output = StringIO()
        with redirect_stdout(output), redirect_stderr(output):
            exit_code = runner.run_contracts(("quality_fixture.does_not_exist",))
        self.assertEqual(exit_code, 1)
        self.assertIn("FAILED (errors=1)", output.getvalue())

    def test_skip_is_rejected(self):
        with tempfile.TemporaryDirectory(prefix="raise-quality-skip-") as tmp:
            root = Path(tmp)
            package = root / "quality_fixture"
            package.mkdir()
            (package / "__init__.py").write_text("", encoding="utf-8")
            (package / "skip_contract.py").write_text(
                "import unittest\n"
                "class SkipContract(unittest.TestCase):\n"
                "    @unittest.skip('synthetic skip')\n"
                "    def test_skip(self):\n"
                "        pass\n",
                encoding="utf-8",
            )
            sys.path.insert(0, str(root))
            try:
                output = StringIO()
                with redirect_stdout(output), redirect_stderr(output):
                    exit_code = runner.run_contracts(("quality_fixture.skip_contract",))
            finally:
                sys.path.remove(str(root))
                sys.modules.pop("quality_fixture.skip_contract", None)
                sys.modules.pop("quality_fixture", None)

        self.assertEqual(exit_code, 1)
        self.assertIn("SKIPPED:", output.getvalue())
        self.assertIn("synthetic skip", output.getvalue())

    def test_passing_module_returns_zero(self):
        with tempfile.TemporaryDirectory(prefix="raise-quality-pass-") as tmp:
            root = Path(tmp)
            package = root / "quality_fixture"
            package.mkdir()
            (package / "__init__.py").write_text("", encoding="utf-8")
            (package / "pass_contract.py").write_text(
                "import unittest\n"
                "class PassContract(unittest.TestCase):\n"
                "    def test_passes(self):\n"
                "        self.assertTrue(True)\n",
                encoding="utf-8",
            )
            sys.path.insert(0, str(root))
            try:
                output = StringIO()
                with redirect_stdout(output), redirect_stderr(output):
                    exit_code = runner.run_contracts(("quality_fixture.pass_contract",))
            finally:
                sys.path.remove(str(root))
                sys.modules.pop("quality_fixture.pass_contract", None)
                sys.modules.pop("quality_fixture", None)

        self.assertEqual(exit_code, 0, output.getvalue())


if __name__ == "__main__":
    unittest.main()
