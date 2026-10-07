from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
TESTS_DIR = ROOT / "tests"


def contract_exit_code(result: unittest.TestResult) -> int:
    if result.skipped or result.expectedFailures:
        return 1
    return 0 if result.wasSuccessful() else 1


def contract_module_names() -> list[str]:
    return sorted(
        path.stem
        for path in TESTS_DIR.glob("test_*.py")
        if path.is_file()
    )


def discovered_test_modules(suite: unittest.TestSuite) -> set[str]:
    modules: set[str] = set()
    for item in suite:
        if isinstance(item, unittest.TestSuite):
            modules.update(discovered_test_modules(item))
            continue
        module = item.__class__.__module__.rsplit(".", 1)[-1]
        modules.add(module)
    return modules


def main() -> int:
    suite = unittest.TestLoader().discover(
        str(TESTS_DIR),
        pattern="test_*.py",
    )
    test_count = suite.countTestCases()
    if test_count == 0:
        print(
            "ERROR: aggregate Python contract discovery found zero tests; "
            "an empty quality suite must fail closed.",
            file=sys.stderr,
        )
        return 1

    expected_modules = contract_module_names()
    discovered_modules = discovered_test_modules(suite)
    missing_modules = sorted(set(expected_modules) - discovered_modules)

    result = unittest.TextTestRunner(
        stream=sys.stdout,
        verbosity=2,
    ).run(suite)

    if result.skipped:
        print(
            f"ERROR: aggregate Python contracts skipped {len(result.skipped)} test(s); "
            "the pinned Ubuntu quality lane must execute every discovered contract.",
            file=sys.stderr,
        )
        for test, reason in result.skipped:
            print(f"SKIPPED: {test.id()}: {reason}", file=sys.stderr)

    if result.expectedFailures:
        print(
            f"ERROR: aggregate Python contracts accepted {len(result.expectedFailures)} "
            "expected failure(s); contract failures may not be downgraded.",
            file=sys.stderr,
        )
        for test, _ in result.expectedFailures:
            print(f"EXPECTED-FAILURE: {test.id()}", file=sys.stderr)

    if missing_modules:
        print(
            "ERROR: aggregate Python contract discovery found tracked test modules "
            "that contributed zero tests; every test_*.py contract module must execute.",
            file=sys.stderr,
        )
        for module in missing_modules:
            print(f"EMPTY-CONTRACT-MODULE: {module}", file=sys.stderr)

    if missing_modules:
        return 1
    return contract_exit_code(result)


if __name__ == "__main__":
    raise SystemExit(main())
