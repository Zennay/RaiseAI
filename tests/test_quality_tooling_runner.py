from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
import importlib.util
from pathlib import Path
import subprocess
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

    def test_tests_package_anchor_is_empty_regular_file(self):
        self.assertTrue(runner.TEST_PACKAGE_INIT.is_file())
        self.assertFalse(runner.TEST_PACKAGE_INIT.is_symlink())
        self.assertEqual(runner.TEST_PACKAGE_INIT.read_bytes(), b"")

    def test_nonempty_tests_package_anchor_fails_before_loading_contracts(self):
        with tempfile.TemporaryDirectory(prefix="raise-quality-package-anchor-") as tmp:
            anchor = Path(tmp) / "__init__.py"
            anchor.write_text("raise RuntimeError('unexpected package side effect')\n", encoding="utf-8")
            original = runner.TEST_PACKAGE_INIT
            runner.TEST_PACKAGE_INIT = anchor
            try:
                output = StringIO()
                with redirect_stdout(output), redirect_stderr(output):
                    exit_code = runner.run_contracts(("quality_fixture.does_not_exist",))
            finally:
                runner.TEST_PACKAGE_INIT = original
        self.assertEqual(exit_code, 1)
        self.assertIn("tests package anchor must remain empty", output.getvalue())
        self.assertNotIn("FAILED (errors=1)", output.getvalue())

    def test_nonisolated_process_is_rejected_before_loading_contracts(self):
        completed = subprocess.run(
            [sys.executable, str(RUNNER)],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(completed.returncode, 1)
        self.assertIn(
            "requires CPython isolated mode (-I)",
            completed.stderr,
        )
        self.assertNotIn("Ran ", completed.stdout + completed.stderr)

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
                    exit_code = runner.run_contracts(
                        ("quality_fixture.empty_contract",),
                        module_root=root,
                    )
            finally:
                sys.path.remove(str(root))
                sys.modules.pop("quality_fixture.empty_contract", None)
                sys.modules.pop("quality_fixture", None)

        self.assertEqual(exit_code, 1)
        self.assertIn(
            "EMPTY-QUALITY-MODULE: quality_fixture.empty_contract",
            output.getvalue(),
        )

    def test_reexported_tests_do_not_mask_empty_allowlisted_module(self):
        with tempfile.TemporaryDirectory(prefix="raise-quality-reexport-") as tmp:
            root = Path(tmp)
            package = root / "quality_fixture"
            package.mkdir()
            (package / "__init__.py").write_text("", encoding="utf-8")
            (package / "source_contract.py").write_text(
                "import unittest\n"
                "class SourceContract(unittest.TestCase):\n"
                "    def test_passes(self):\n"
                "        self.assertTrue(True)\n",
                encoding="utf-8",
            )
            (package / "reexport_contract.py").write_text(
                "from .source_contract import SourceContract\n",
                encoding="utf-8",
            )
            sys.path.insert(0, str(root))
            try:
                output = StringIO()
                with redirect_stdout(output), redirect_stderr(output):
                    exit_code = runner.run_contracts(
                        ("quality_fixture.reexport_contract",),
                        module_root=root,
                    )
            finally:
                sys.path.remove(str(root))
                sys.modules.pop("quality_fixture.reexport_contract", None)
                sys.modules.pop("quality_fixture.source_contract", None)
                sys.modules.pop("quality_fixture", None)

        self.assertEqual(exit_code, 1)
        self.assertIn(
            "EMPTY-QUALITY-MODULE: quality_fixture.reexport_contract",
            output.getvalue(),
        )

    def test_inherited_tests_do_not_mask_module_without_own_test_methods(self):
        with tempfile.TemporaryDirectory(prefix="raise-quality-inherited-") as tmp:
            root = Path(tmp)
            package = root / "quality_fixture"
            package.mkdir()
            (package / "__init__.py").write_text("", encoding="utf-8")
            (package / "source_contract.py").write_text(
                "import unittest\n"
                "class SourceContract(unittest.TestCase):\n"
                "    def test_passes(self):\n"
                "        self.assertTrue(True)\n",
                encoding="utf-8",
            )
            (package / "inherited_contract.py").write_text(
                "from .source_contract import SourceContract\n"
                "class InheritedContract(SourceContract):\n"
                "    pass\n",
                encoding="utf-8",
            )
            sys.path.insert(0, str(root))
            try:
                output = StringIO()
                with redirect_stdout(output), redirect_stderr(output):
                    exit_code = runner.run_contracts(
                        ("quality_fixture.inherited_contract",),
                        module_root=root,
                    )
            finally:
                sys.path.remove(str(root))
                sys.modules.pop("quality_fixture.inherited_contract", None)
                sys.modules.pop("quality_fixture.source_contract", None)
                sys.modules.pop("quality_fixture", None)

        self.assertEqual(exit_code, 1)
        self.assertIn(
            "EMPTY-QUALITY-MODULE: quality_fixture.inherited_contract",
            output.getvalue(),
        )

    def test_symlinked_module_is_rejected_before_import(self):
        with tempfile.TemporaryDirectory(prefix="raise-quality-link-") as tmp:
            root = Path(tmp)
            package = root / "quality_fixture"
            package.mkdir()
            (package / "__init__.py").write_text("", encoding="utf-8")
            target = root / "linked_contract.py"
            target.write_text(
                'raise RuntimeError("symlink target must not execute")\n',
                encoding="utf-8",
            )
            (package / "linked_contract.py").symlink_to(target)
            sys.path.insert(0, str(root))
            try:
                output = StringIO()
                with redirect_stdout(output), redirect_stderr(output):
                    exit_code = runner.run_contracts(
                        ("quality_fixture.linked_contract",),
                        module_root=root,
                    )
            finally:
                sys.path.remove(str(root))
                sys.modules.pop("quality_fixture.linked_contract", None)
                sys.modules.pop("quality_fixture", None)

        rendered = output.getvalue()
        self.assertEqual(exit_code, 1, rendered)
        self.assertIn(
            "UNSAFE-QUALITY-MODULE: quality_fixture.linked_contract: "
            "symbolic links are forbidden",
            rendered,
        )
        self.assertNotIn("symlink target must not execute", rendered)

    def test_symlinked_package_is_rejected_before_import(self):
        with tempfile.TemporaryDirectory(prefix="raise-quality-package-link-") as tmp:
            root = Path(tmp)
            real_package = root / "real_quality_fixture"
            real_package.mkdir()
            (real_package / "__init__.py").write_text("", encoding="utf-8")
            (real_package / "linked_contract.py").write_text(
                'raise RuntimeError("symlinked package must not execute")\n',
                encoding="utf-8",
            )
            (root / "quality_fixture").symlink_to(real_package, target_is_directory=True)
            sys.path.insert(0, str(root))
            try:
                output = StringIO()
                with redirect_stdout(output), redirect_stderr(output):
                    exit_code = runner.run_contracts(
                        ("quality_fixture.linked_contract",),
                        module_root=root,
                    )
            finally:
                sys.path.remove(str(root))
                sys.modules.pop("quality_fixture.linked_contract", None)
                sys.modules.pop("quality_fixture", None)

        rendered = output.getvalue()
        self.assertEqual(exit_code, 1, rendered)
        self.assertIn(
            "UNSAFE-QUALITY-MODULE: quality_fixture/: "
            "symbolic link directories are forbidden",
            rendered,
        )
        self.assertNotIn("symlinked package must not execute", rendered)

    def test_nonregular_module_entry_is_rejected_before_import(self):
        with tempfile.TemporaryDirectory(prefix="raise-quality-nonregular-") as tmp:
            root = Path(tmp)
            package = root / "quality_fixture"
            package.mkdir()
            (package / "__init__.py").write_text("", encoding="utf-8")
            (package / "directory_contract.py").mkdir()
            output = StringIO()
            with redirect_stdout(output), redirect_stderr(output):
                exit_code = runner.run_contracts(
                    ("quality_fixture.directory_contract",),
                    module_root=root,
                )

        rendered = output.getvalue()
        self.assertEqual(exit_code, 1, rendered)
        self.assertIn(
            "UNSAFE-QUALITY-MODULE: quality_fixture.directory_contract: "
            "must be a regular file",
            rendered,
        )

    def test_missing_module_is_rejected_before_import_resolution(self):
        with tempfile.TemporaryDirectory(prefix="raise-quality-missing-") as tmp:
            root = Path(tmp)
            package = root / "quality_fixture"
            package.mkdir()
            (package / "__init__.py").write_text("", encoding="utf-8")
            output = StringIO()
            with redirect_stdout(output), redirect_stderr(output):
                exit_code = runner.run_contracts(
                    ("quality_fixture.does_not_exist",),
                    module_root=root,
                )

        rendered = output.getvalue()
        self.assertEqual(exit_code, 1, rendered)
        self.assertIn("unsafe module inputs", rendered)
        self.assertIn(
            "UNSAFE-QUALITY-MODULE: quality_fixture.does_not_exist: lstat failed:",
            rendered,
        )
        self.assertNotIn("FAILED (errors=1)", rendered)

    def test_existing_module_runtime_error_fails_closed_without_escaping(self):
        with tempfile.TemporaryDirectory(prefix="raise-quality-runtime-error-") as tmp:
            root = Path(tmp)
            package = root / "quality_fixture"
            package.mkdir()
            (package / "__init__.py").write_text("", encoding="utf-8")
            (package / "runtime_error_contract.py").write_text(
                'raise RuntimeError("synthetic import failure")\n',
                encoding="utf-8",
            )
            sys.path.insert(0, str(root))
            try:
                output = StringIO()
                with redirect_stdout(output), redirect_stderr(output):
                    exit_code = runner.run_contracts(
                        ("quality_fixture.runtime_error_contract",),
                        module_root=root,
                    )
            finally:
                sys.path.remove(str(root))
                sys.modules.pop("quality_fixture.runtime_error_contract", None)
                sys.modules.pop("quality_fixture", None)

        rendered = output.getvalue()
        self.assertEqual(exit_code, 1, rendered)
        self.assertIn(
            "LOAD-QUALITY-MODULE: quality_fixture.runtime_error_contract: RuntimeError",
            rendered,
        )
        self.assertNotIn("synthetic import failure", rendered)

    def test_existing_module_import_error_remains_a_unittest_failure(self):
        with tempfile.TemporaryDirectory(prefix="raise-quality-import-error-") as tmp:
            root = Path(tmp)
            package = root / "quality_fixture"
            package.mkdir()
            (package / "__init__.py").write_text("", encoding="utf-8")
            (package / "import_error_contract.py").write_text(
                "import dependency_that_must_not_exist\n",
                encoding="utf-8",
            )
            sys.path.insert(0, str(root))
            try:
                output = StringIO()
                with redirect_stdout(output), redirect_stderr(output):
                    exit_code = runner.run_contracts(
                        ("quality_fixture.import_error_contract",),
                        module_root=root,
                    )
            finally:
                sys.path.remove(str(root))
                sys.modules.pop("quality_fixture.import_error_contract", None)
                sys.modules.pop("quality_fixture", None)

        rendered = output.getvalue()
        self.assertEqual(exit_code, 1, rendered)
        self.assertIn("FAILED (errors=1)", rendered)
        self.assertIn("dependency_that_must_not_exist", rendered)

    def test_system_exit_zero_during_import_fails_closed(self):
        with tempfile.TemporaryDirectory(prefix="raise-quality-system-exit-") as tmp:
            root = Path(tmp)
            package = root / "quality_fixture"
            package.mkdir()
            (package / "__init__.py").write_text("", encoding="utf-8")
            (package / "system_exit_contract.py").write_text(
                "raise SystemExit(0)\n",
                encoding="utf-8",
            )
            sys.path.insert(0, str(root))
            try:
                output = StringIO()
                with redirect_stdout(output), redirect_stderr(output):
                    exit_code = runner.run_contracts(
                        ("quality_fixture.system_exit_contract",),
                        module_root=root,
                    )
            finally:
                sys.path.remove(str(root))
                sys.modules.pop("quality_fixture.system_exit_contract", None)
                sys.modules.pop("quality_fixture", None)

        rendered = output.getvalue()
        self.assertEqual(exit_code, 1, rendered)
        self.assertIn(
            "LOAD-QUALITY-MODULE: quality_fixture.system_exit_contract: SystemExit",
            rendered,
        )

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
                    exit_code = runner.run_contracts(
                        ("quality_fixture.skip_contract",),
                        module_root=root,
                    )
            finally:
                sys.path.remove(str(root))
                sys.modules.pop("quality_fixture.skip_contract", None)
                sys.modules.pop("quality_fixture", None)

        self.assertEqual(exit_code, 1)
        self.assertIn("SKIPPED:", output.getvalue())
        self.assertIn("synthetic skip", output.getvalue())

    def test_expected_failure_is_rejected(self):
        with tempfile.TemporaryDirectory(prefix="raise-quality-xfail-") as tmp:
            root = Path(tmp)
            package = root / "quality_fixture"
            package.mkdir()
            (package / "__init__.py").write_text("", encoding="utf-8")
            (package / "xfail_contract.py").write_text(
                "import unittest\n"
                "class ExpectedFailureContract(unittest.TestCase):\n"
                "    @unittest.expectedFailure\n"
                "    def test_expected_failure(self):\n"
                "        self.assertEqual(1, 2)\n",
                encoding="utf-8",
            )
            sys.path.insert(0, str(root))
            try:
                output = StringIO()
                with redirect_stdout(output), redirect_stderr(output):
                    exit_code = runner.run_contracts(
                        ("quality_fixture.xfail_contract",),
                        module_root=root,
                    )
            finally:
                sys.path.remove(str(root))
                sys.modules.pop("quality_fixture.xfail_contract", None)
                sys.modules.pop("quality_fixture", None)

        self.assertEqual(exit_code, 1)
        self.assertIn("EXPECTED-FAILURE:", output.getvalue())

    def test_unexpected_success_is_rejected(self):
        with tempfile.TemporaryDirectory(prefix="raise-quality-xpass-") as tmp:
            root = Path(tmp)
            package = root / "quality_fixture"
            package.mkdir()
            (package / "__init__.py").write_text("", encoding="utf-8")
            (package / "xpass_contract.py").write_text(
                "import unittest\n"
                "class UnexpectedSuccessContract(unittest.TestCase):\n"
                "    @unittest.expectedFailure\n"
                "    def test_unexpected_success(self):\n"
                "        self.assertEqual(1, 1)\n",
                encoding="utf-8",
            )
            sys.path.insert(0, str(root))
            try:
                output = StringIO()
                with redirect_stdout(output), redirect_stderr(output):
                    exit_code = runner.run_contracts(
                        ("quality_fixture.xpass_contract",),
                        module_root=root,
                    )
            finally:
                sys.path.remove(str(root))
                sys.modules.pop("quality_fixture.xpass_contract", None)
                sys.modules.pop("quality_fixture", None)

        self.assertEqual(exit_code, 1)
        self.assertIn("UNEXPECTED-SUCCESS:", output.getvalue())

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
                    exit_code = runner.run_contracts(
                        ("quality_fixture.pass_contract",),
                        module_root=root,
                    )
            finally:
                sys.path.remove(str(root))
                sys.modules.pop("quality_fixture.pass_contract", None)
                sys.modules.pop("quality_fixture", None)

        self.assertEqual(exit_code, 0, output.getvalue())


if __name__ == "__main__":
    unittest.main()
