from contextlib import chdir
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]

QUALITY_MODULES = (
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


def build_suite(
    modules: tuple[str, ...] = QUALITY_MODULES,
) -> tuple[unittest.TestSuite, list[str]]:
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    empty_modules: list[str] = []

    for module in modules:
        module_suite = loader.loadTestsFromName(module)
        if module_suite.countTestCases() == 0:
            empty_modules.append(module)
        suite.addTests(module_suite)

    return suite, empty_modules


def result_exit_code(result: unittest.TestResult) -> int:
    if result.skipped or result.expectedFailures or result.unexpectedSuccesses:
        return 1
    return 0 if result.wasSuccessful() else 1


def run_contracts(modules: tuple[str, ...] = QUALITY_MODULES) -> int:
    if not modules:
        print("ERROR: quality tooling module allowlist is empty.", file=sys.stderr)
        return 1

    if len(set(modules)) != len(modules):
        print("ERROR: quality tooling module allowlist contains duplicates.", file=sys.stderr)
        return 1

    suite, empty_modules = build_suite(modules)
    if empty_modules:
        print(
            "ERROR: quality tooling allowlist contains module(s) with zero tests.",
            file=sys.stderr,
        )
        for module in empty_modules:
            print(f"EMPTY-QUALITY-MODULE: {module}", file=sys.stderr)
        return 1

    result = unittest.TextTestRunner(stream=sys.stdout, verbosity=2).run(suite)

    if result.skipped:
        print(
            f"ERROR: quality tooling regressions skipped {len(result.skipped)} test(s).",
            file=sys.stderr,
        )
        for test, reason in result.skipped:
            print(f"SKIPPED: {test.id()}: {reason}", file=sys.stderr)

    if result.expectedFailures:
        print(
            "ERROR: quality tooling regressions contain expected failure(s).",
            file=sys.stderr,
        )
        for test, _ in result.expectedFailures:
            print(f"EXPECTED-FAILURE: {test.id()}", file=sys.stderr)

    if result.unexpectedSuccesses:
        print(
            "ERROR: quality tooling regressions contain unexpected success(es).",
            file=sys.stderr,
        )
        for test in result.unexpectedSuccesses:
            print(f"UNEXPECTED-SUCCESS: {test.id()}", file=sys.stderr)

    return result_exit_code(result)


def main() -> int:
    root = str(ROOT)
    if root not in sys.path:
        sys.path.insert(0, root)

    with chdir(ROOT):
        return run_contracts()


if __name__ == "__main__":
    raise SystemExit(main())
