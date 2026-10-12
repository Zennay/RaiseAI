"""Reject JUnit assumptions and explicit aborted-test constructors in Watch tests.

Neither the existing @Ignore/@Disabled source guard nor nonempty JUnit suites
catch tests that silently skip at runtime through Assume/Assumptions.
This scan is source-only: it does not establish Android/JVM or Watch acceptance.
"""
from __future__ import annotations

from pathlib import Path
import re
import unittest

if __package__:
    from .test_kotlin_junit_disable_contract import kotlin_code_only, kotlin_test_paths
else:
    from test_kotlin_junit_disable_contract import kotlin_code_only, kotlin_test_paths


ROOT = Path(__file__).resolve().parents[1]
ASSUMPTION_CLASSES = frozenset({
    "org.junit.Assume",
    "org.junit.jupiter.api.Assumptions",
})
ABORT_CLASS = "org.opentest4j.TestAbortedException"
SKIP_METHODS = frozenset({
    "assumeTrue", "assumeFalse", "assumeNotNull", "assumeNoException",
    "assumeThat", "assumingThat",
})
IMPORT = re.compile(
    r"(?m)^[ \t]*import[ \t]+"
    r"(org\.junit\.Assume|org\.junit\.jupiter\.api\.Assumptions|"
    r"org\.opentest4j\.TestAbortedException)"
    r"(?:\.(assumeTrue|assumeFalse|assumeNotNull|assumeNoException|"
    r"assumeThat|assumingThat|\*))?"
    r"(?:[ \t]+as[ \t]+([A-Za-z_][A-Za-z_0-9]*))?[ \t]*$"
)
TYPEALIAS = re.compile(
    r"(?m)^[ \t]*(?:public[ \t]+|private[ \t]+|internal[ \t]+)?"
    r"typealias[ \t]+([A-Za-z_][A-Za-z_0-9]*)[ \t]*=[ \t]*"
    r"([A-Za-z_][A-Za-z_0-9]*(?:\.[A-Za-z_][A-Za-z_0-9]*)*)[ \t]*$"
)
CALL = re.compile(
    r"(?<![A-Za-z_0-9])"
    r"([A-Za-z_][A-Za-z_0-9]*(?:\.[A-Za-z_][A-Za-z_0-9]*)*)"
    r"[ \t]*\("
)


def junit_runtime_aborts(source: str) -> list[tuple[int, str]]:
    """Return real source positions for known JUnit assumptions/aborts.

    Qualifiers are resolved from exact JUnit imports and Kotlin typealiases,
    not name-similar unrelated libraries. Import aliases and wildcard static
    function imports are included; comments and string fixtures are masked.
    """
    code = kotlin_code_only(source)
    assume_classes = set(ASSUMPTION_CLASSES)
    aborted_classes = {ABORT_CLASS}
    functions: set[str] = set()

    for match in IMPORT.finditer(code):
        source_name, function, alias = match.groups()
        if source_name == ABORT_CLASS:
            aborted_classes.add(alias or "TestAbortedException")
        elif function == "*":
            functions.update(SKIP_METHODS)
        elif function:
            functions.add(alias or function)
        else:
            assume_classes.add(alias or source_name.rsplit(".", 1)[-1])

    # Resolve typealiases, including forward and reverse chains, to JUnit
    # classes. A failed convergence must not yield a permissive shortcut.
    aliases = TYPEALIAS.findall(code)
    for _ in range(len(aliases) + 1):
        changed = False
        for name, target in aliases:
            if target in assume_classes and name not in assume_classes:
                assume_classes.add(name)
                changed = True
            if target in aborted_classes and name not in aborted_classes:
                aborted_classes.add(name)
                changed = True
        if not changed:
            break

    violations = []
    for match in CALL.finditer(code):
        symbol = match.group(1)
        segments = symbol.rsplit(".", 1)
        is_assumption = (
            (len(segments) == 1 and symbol in functions)
            or (len(segments) == 2 and segments[0] in assume_classes
                and segments[1] in SKIP_METHODS)
        )
        is_abort = symbol in aborted_classes
        if is_assumption or is_abort:
            line = code.count("\n", 0, match.start()) + 1
            violations.append((line, symbol))
    return violations


class KotlinJunitRuntimeAbortContract(unittest.TestCase):
    def test_repository_kotlin_tests_have_no_runtime_skip_constructs(self):
        paths = kotlin_test_paths()
        self.assertTrue(paths, "Kotlin test source inventory must not disappear")
        violations = []
        for path in paths:
            self.assertTrue(path.is_file() and not path.is_symlink())
            for line, symbol in junit_runtime_aborts(path.read_text(encoding="utf-8")):
                violations.append(f"{path.relative_to(ROOT)}:{line}: {symbol}")
        self.assertEqual([], violations, "\n".join(violations))

    def test_junit4_qualified_assumptions_are_rejected(self):
        source = (
            "org.junit.Assume.assumeTrue(false)\n"
            "org.junit.Assume.assumeFalse(true)\n"
            "org.junit.Assume.assumeNoException(error)\n"
        )
        self.assertEqual(
            [(1, "org.junit.Assume.assumeTrue"),
             (2, "org.junit.Assume.assumeFalse"),
             (3, "org.junit.Assume.assumeNoException")],
            junit_runtime_aborts(source),
        )

    def test_junit5_qualified_assumptions_are_rejected(self):
        source = (
            "org.junit.jupiter.api.Assumptions.assumeTrue(false)\n"
            "org.junit.jupiter.api.Assumptions.assumingThat(false) {}\n"
        )
        self.assertEqual(
            [(1, "org.junit.jupiter.api.Assumptions.assumeTrue"),
             (2, "org.junit.jupiter.api.Assumptions.assumingThat")],
            junit_runtime_aborts(source),
        )

    def test_junit4_class_import_is_rejected(self):
        self.assertEqual(
            [(2, "Assume.assumeNotNull")],
            junit_runtime_aborts(
                "import org.junit.Assume\nAssume.assumeNotNull(null)\n"
            ),
        )

    def test_junit5_class_alias_import_is_rejected(self):
        self.assertEqual(
            [(2, "Conditional.assumeFalse")],
            junit_runtime_aborts(
                "import org.junit.jupiter.api.Assumptions as Conditional\n"
                "Conditional.assumeFalse(true)\n"
            ),
        )

    def test_junit4_function_import_and_alias_are_rejected(self):
        self.assertEqual(
            [(3, "assumeTrue"), (4, "AvoidRun")],
            junit_runtime_aborts(
                "import org.junit.Assume.assumeTrue\n"
                "import org.junit.Assume.assumeThat as AvoidRun\n"
                "assumeTrue(false)\n"
                "AvoidRun(input, matcher)\n"
            ),
        )

    def test_junit5_function_import_alias_is_rejected(self):
        self.assertEqual(
            [(2, "DropTest")],
            junit_runtime_aborts(
                "import org.junit.jupiter.api.Assumptions.assumingThat as DropTest\n"
                "DropTest(false) {}\n"
            ),
        )

    def test_junit_static_wildcard_import_is_rejected(self):
        self.assertEqual(
            [(2, "assumeFalse")],
            junit_runtime_aborts(
                "import org.junit.Assume.*\nassumeFalse(true)\n"
            ),
        )

    def test_junit_abort_exception_import_is_rejected(self):
        self.assertEqual(
            [(2, "TestAbortedException")],
            junit_runtime_aborts(
                "import org.opentest4j.TestAbortedException\n"
                'throw TestAbortedException("not today")\n'
            ),
        )

    def test_abort_exception_alias_and_qualified_are_rejected(self):
        self.assertEqual(
            [(2, "SilentAbort"), (3, "org.opentest4j.TestAbortedException")],
            junit_runtime_aborts(
                "import org.opentest4j.TestAbortedException as SilentAbort\n"
                'throw SilentAbort("skip")\n'
                'throw org.opentest4j.TestAbortedException("skip")\n'
            ),
        )

    def test_reverse_declared_long_class_typealias_chain_is_rejected(self):
        aliases = [
            f"typealias Alias{index} = "
            + ("org.junit.Assume" if index == 0 else f"Alias{index - 1}")
            for index in range(70)
        ]
        source = "\n".join(reversed(aliases)) + "\nAlias69.assumeTrue(false)\n"
        self.assertEqual(
            [(71, "Alias69.assumeTrue")],
            junit_runtime_aborts(source),
        )

    def test_abort_exception_typealias_is_rejected(self):
        self.assertEqual(
            [(2, "AbortNow")],
            junit_runtime_aborts(
                "typealias AbortNow = org.opentest4j.TestAbortedException\n"
                'throw AbortNow("bad")\n'
            ),
        )

    def test_unrelated_library_assume_calls_are_not_junit(self):
        self.assertEqual(
            [],
            junit_runtime_aborts(
                "import example.metrics.Assume\n"
                "import example.metrics.assumeTrue\n"
                "Assume.assumeTrue(true)\n"
                "assumeTrue(true)\n"
                "other.Assumptions.assumingThat(true) {}\n"
            ),
        )

    def test_nested_comments_and_strings_cannot_forge_a_skip(self):
        self.assertEqual(
            [],
            junit_runtime_aborts(
                "import org.junit.Assume\n"
                "// Assume.assumeTrue(false)\n"
                "/* Assume.assumeFalse(true)\n"
                "   /* Assume.assumeNotNull(null) */ */\n"
                'val s = """\nAssume.assumeTrue(false)\n"""\n'
                'val t = "Assume.assumeFalse(true)"\n'
                "val c = 'X'\n"
            ),
        )

    def test_malformed_source_fails_closed(self):
        for malformed in ('val s = """unfinished', '/* unfinished'):
            with self.subTest(malformed=malformed):
                with self.assertRaises(ValueError):
                    junit_runtime_aborts(malformed)

    def test_regular_assertions_and_expected_exceptions_are_allowed(self):
        self.assertEqual(
            [],
            junit_runtime_aborts(
                "import org.junit.Assert.assertTrue\n"
                "import org.junit.Test\n"
                "@Test(expected = IllegalArgumentException::class)\n"
                "fun rejectsInvalid() { assertTrue(true) }\n"
            ),
        )


if __name__ == "__main__":
    unittest.main()
