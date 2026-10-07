from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
TESTS_DIR = ROOT / "tests"


def contract_exit_code(result: unittest.TestResult) -> int:
    if result.skipped:
        return 1
    return 0 if result.wasSuccessful() else 1


def main() -> int:
    suite = unittest.defaultTestLoader.discover(
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

    return contract_exit_code(result)


if __name__ == "__main__":
    raise SystemExit(main())
