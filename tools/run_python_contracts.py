from contextlib import chdir
from pathlib import Path
import os
import stat
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
TESTS_DIR = ROOT / "tests"


def contract_exit_code(result: unittest.TestResult) -> int:
    if result.skipped or result.expectedFailures:
        return 1
    return 0 if result.wasSuccessful() else 1


def invalid_contract_package_links() -> list[str]:
    invalid: list[str] = []
    for root, dirnames, _ in os.walk(TESTS_DIR, topdown=True, followlinks=False):
        root_path = Path(root)
        for dirname in list(dirnames):
            path = root_path / dirname
            try:
                mode = path.lstat().st_mode
            except OSError as exc:
                invalid.append(f"{path.relative_to(TESTS_DIR)}: lstat failed: {exc}")
                dirnames.remove(dirname)
                continue
            if stat.S_ISLNK(mode):
                invalid.append(
                    f"{path.relative_to(TESTS_DIR).as_posix()}/: "
                    "symbolic link directories are forbidden"
                )
                dirnames.remove(dirname)
    return invalid


def contract_module_paths() -> list[Path]:
    return sorted(TESTS_DIR.rglob("test_*.py"))


def unsafe_contract_module_paths(paths: list[Path]) -> list[str]:
    unsafe: list[str] = []
    for path in paths:
        try:
            mode = path.lstat().st_mode
        except OSError as exc:
            unsafe.append(f"{path.name}: lstat failed: {exc}")
            continue

        if stat.S_ISLNK(mode):
            unsafe.append(f"{path.name}: symbolic links are forbidden")
        elif not stat.S_ISREG(mode):
            unsafe.append(f"{path.name}: must be a regular file")
    return unsafe


def contract_module_names(paths: list[Path] | None = None) -> list[str]:
    if paths is None:
        paths = contract_module_paths()
    return sorted(path.stem for path in paths)


def discovered_test_modules(suite: unittest.TestSuite) -> set[str]:
    modules: set[str] = set()
    for item in suite:
        if isinstance(item, unittest.TestSuite):
            modules.update(discovered_test_modules(item))
            continue
        module = item.__class__.__module__.rsplit(".", 1)[-1]
        modules.add(module)
    return modules


def run_contracts() -> int:
    invalid_packages = invalid_contract_package_links()
    if invalid_packages:
        print(
            "ERROR: aggregate Python contract discovery found invalid package entries; "
            "test package directories may not use symlinks.",
            file=sys.stderr,
        )
        for violation in invalid_packages:
            print(f"INVALID-CONTRACT-PACKAGE: {violation}", file=sys.stderr)
        return 1

    module_paths = contract_module_paths()
    unsafe_modules = unsafe_contract_module_paths(module_paths)
    if unsafe_modules:
        print(
            "ERROR: aggregate Python contract discovery found unsafe test module "
            "entries; test_*.py inputs must be regular files and may not use symlinks.",
            file=sys.stderr,
        )
        for violation in unsafe_modules:
            print(f"UNSAFE-CONTRACT-MODULE: {violation}", file=sys.stderr)
        return 1

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

    expected_modules = contract_module_names(module_paths)
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


def main() -> int:
    with chdir(ROOT):
        return run_contracts()


if __name__ == "__main__":
    raise SystemExit(main())
