from contextlib import chdir
from pathlib import Path
import hashlib
import stat
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
TEST_PACKAGE_INIT = ROOT / "tests" / "__init__.py"

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


def validate_test_package_anchor() -> str | None:
    try:
        mode = TEST_PACKAGE_INIT.lstat().st_mode
    except OSError as exc:
        return f"tests package anchor is unavailable: {exc}"
    if stat.S_ISLNK(mode):
        return "tests package anchor may not be a symbolic link"
    if not stat.S_ISREG(mode):
        return "tests package anchor must be a regular file"
    try:
        content = TEST_PACKAGE_INIT.read_bytes()
    except OSError as exc:
        return f"tests package anchor cannot be read: {exc}"
    if content != b"":
        return "tests package anchor must remain empty"
    return None


def quality_module_input_violations(
    modules: tuple[str, ...],
    module_root: Path,
) -> list[str]:
    violations: list[str] = []
    checked_packages: set[Path] = set()

    for module in modules:
        parts = module.split(".")
        if not parts or any(not part.isidentifier() for part in parts):
            violations.append(f"{module}: invalid module identity")
            continue

        for depth in range(1, len(parts)):
            package = module_root.joinpath(*parts[:depth])
            if package in checked_packages:
                continue
            checked_packages.add(package)
            try:
                mode = package.lstat().st_mode
            except OSError as exc:
                violations.append(
                    f"{'.'.join(parts[:depth])}/: lstat failed: {exc}"
                )
                continue
            if stat.S_ISLNK(mode):
                violations.append(
                    f"{'.'.join(parts[:depth])}/: symbolic link directories are forbidden"
                )
            elif not stat.S_ISDIR(mode):
                violations.append(
                    f"{'.'.join(parts[:depth])}/: must be a regular directory"
                )

        path = module_root.joinpath(*parts).with_suffix(".py")
        try:
            mode = path.lstat().st_mode
        except OSError as exc:
            violations.append(f"{module}: lstat failed: {exc}")
            continue
        if stat.S_ISLNK(mode):
            violations.append(f"{module}: symbolic links are forbidden")
        elif not stat.S_ISREG(mode):
            violations.append(f"{module}: must be a regular file")

    return violations


def quality_module_path(module: str, module_root: Path) -> Path:
    return module_root.joinpath(*module.split(".")).with_suffix(".py")


def quality_module_digest(module: str, module_root: Path) -> tuple[str | None, str | None]:
    path = quality_module_path(module, module_root)
    try:
        content = path.read_bytes()
    except OSError as exc:
        return None, f"{module}: read failed: {exc}"
    return hashlib.sha256(content).hexdigest(), None


def quality_module_digest_snapshot(
    modules: tuple[str, ...],
    module_root: Path,
) -> tuple[dict[str, str], list[str]]:
    digests: dict[str, str] = {}
    errors: list[str] = []
    for module in modules:
        digest, error = quality_module_digest(module, module_root)
        if error is not None:
            errors.append(error)
            continue
        assert digest is not None
        digests[module] = digest
    return digests, errors


def suite_test_origins(suite: unittest.TestSuite) -> set[tuple[str, str]]:
    origins: set[tuple[str, str]] = set()
    for item in suite:
        if isinstance(item, unittest.TestSuite):
            origins.update(suite_test_origins(item))
            continue
        class_module = item.__class__.__module__
        method_module = ""
        method_name = getattr(item, "_testMethodName", "")
        if method_name:
            method = getattr(item.__class__, method_name, None)
            method_module = getattr(method, "__module__", "")
        origins.add((class_module, method_module))
    return origins


def build_suite(
    modules: tuple[str, ...] = QUALITY_MODULES,
    *,
    module_root: Path = ROOT,
    expected_digests: dict[str, str] | None = None,
) -> tuple[unittest.TestSuite, list[str], list[str], list[str]]:
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    empty_modules: list[str] = []
    load_errors: list[str] = []
    changed_inputs: list[str] = []

    for module in modules:
        module_violations = quality_module_input_violations((module,), module_root)
        if module_violations:
            changed_inputs.extend(module_violations)
            continue

        if expected_digests is not None:
            digest, digest_error = quality_module_digest(module, module_root)
            if digest_error is not None:
                changed_inputs.append(digest_error)
                continue
            if digest != expected_digests.get(module):
                changed_inputs.append(f"{module}: content changed after preflight")
                continue

        errors_before = len(loader.errors)
        try:
            module_suite = loader.loadTestsFromName(module)
        except BaseException as exc:
            load_errors.append(f"{module}: {type(exc).__name__}")
            continue
        import_failed = len(loader.errors) != errors_before
        owns_test = (module, module) in suite_test_origins(module_suite)
        if not import_failed and not owns_test:
            empty_modules.append(module)
        suite.addTests(module_suite)

    return suite, empty_modules, load_errors, changed_inputs


def result_exit_code(result: unittest.TestResult) -> int:
    if result.skipped or result.expectedFailures or result.unexpectedSuccesses:
        return 1
    return 0 if result.wasSuccessful() else 1


def run_contracts(
    modules: tuple[str, ...] = QUALITY_MODULES,
    *,
    module_root: Path = ROOT,
) -> int:
    anchor_error = validate_test_package_anchor()
    if anchor_error is not None:
        print(f"ERROR: {anchor_error}.", file=sys.stderr)
        return 1

    if not modules:
        print("ERROR: quality tooling module allowlist is empty.", file=sys.stderr)
        return 1

    if len(set(modules)) != len(modules):
        print("ERROR: quality tooling module allowlist contains duplicates.", file=sys.stderr)
        return 1

    unsafe_inputs = quality_module_input_violations(modules, module_root)
    if unsafe_inputs:
        print(
            "ERROR: quality tooling allowlist contains unsafe module inputs; "
            "modules must be regular files beneath regular package directories.",
            file=sys.stderr,
        )
        for violation in unsafe_inputs:
            print(f"UNSAFE-QUALITY-MODULE: {violation}", file=sys.stderr)
        return 1

    expected_digests, digest_errors = quality_module_digest_snapshot(
        modules,
        module_root,
    )
    if digest_errors:
        print(
            "ERROR: quality tooling module inputs could not be read for provenance.",
            file=sys.stderr,
        )
        for error in digest_errors:
            print(f"UNREADABLE-QUALITY-MODULE: {error}", file=sys.stderr)
        return 1

    suite, empty_modules, load_errors, changed_inputs = build_suite(
        modules,
        module_root=module_root,
        expected_digests=expected_digests,
    )
    if changed_inputs:
        print(
            "ERROR: quality tooling module inputs changed after preflight.",
            file=sys.stderr,
        )
        for violation in changed_inputs:
            print(f"CHANGED-QUALITY-MODULE: {violation}", file=sys.stderr)
        return 1

    if load_errors:
        print(
            "ERROR: quality tooling module import raised outside unittest loader handling.",
            file=sys.stderr,
        )
        for error in load_errors:
            print(f"LOAD-QUALITY-MODULE: {error}", file=sys.stderr)
        return 1

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
    if sys.flags.isolated != 1:
        print(
            "ERROR: quality tooling runner requires CPython isolated mode (-I).",
            file=sys.stderr,
        )
        return 1

    root = str(ROOT)
    if root not in sys.path:
        sys.path.insert(0, root)

    with chdir(ROOT):
        return run_contracts(module_root=ROOT)


if __name__ == "__main__":
    raise SystemExit(main())
