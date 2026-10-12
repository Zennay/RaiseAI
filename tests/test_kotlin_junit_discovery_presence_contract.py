"""Fail closed when a Kotlin JUnit suite silently contributes no test methods.

The hosted Python quality gate is not a JVM or physical Watch acceptance run.
"""
from __future__ import annotations

from pathlib import Path
import re
import unittest

from tests.test_kotlin_junit_disable_contract import kotlin_code_only


ROOT = Path(__file__).resolve().parents[1]
JUNIT = frozenset({"org.junit.Test", "org.junit.jupiter.api.Test"})
IMPORT = re.compile(
    r"(?m)^[ \t]*import[ \t]+"
    r"(org\.junit\.Test|org\.junit\.jupiter\.api\.Test)"
    r"(?:[ \t]+as[ \t]+([A-Za-z_][A-Za-z_0-9]*))?[ \t]*$"
)
ANNOTATION = re.compile(r"@([A-Za-z_][A-Za-z_0-9]*(?:\.[A-Za-z_][A-Za-z_0-9]*)*)")
FUNCTION = re.compile(
    r"(?:(?:public|private|protected|internal|open|final|override|suspend|"
    r"inline|tailrec|operator|infix|abstract|external)\s+)*"
    r"fun\s+(?:<[^<>\n]+>\s*)?"
    r"(?:[A-Za-z_][A-Za-z_0-9]*\.)?"
    r"[A-Za-z_][A-Za-z_0-9]*\s*\("
)


def junit_suite_paths(root: Path = ROOT) -> list[Path]:
    paths = []
    for subpath in ("app/src/test", "app/src/androidTest"):
        base = root / subpath
        if base.is_dir():
            paths.extend(base.rglob("*Test.kt"))
    return sorted(paths)


def _annotation_args_end(code: str, offset: int) -> int | None:
    if offset >= len(code) or code[offset] != "(":
        return offset
    depth = 0
    while offset < len(code):
        char = code[offset]
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth == 0:
                return offset + 1
        elif char in "{}":
            return None
        offset += 1
    return None


def junit_method_count(source: str) -> int:
    """Count syntactically attached JUnit test annotations, not raw @Test text."""
    code = kotlin_code_only(source)
    names = set(JUNIT)
    for match in IMPORT.finditer(code):
        names.add(match.group(2) or "Test")
    count = 0
    for match in ANNOTATION.finditer(code):
        if match.group(1) not in names:
            continue
        offset = match.end()
        while offset < len(code) and code[offset].isspace():
            offset += 1
        offset = _annotation_args_end(code, offset)
        if offset is None:
            continue
        while True:
            while offset < len(code) and code[offset].isspace():
                offset += 1
            following = ANNOTATION.match(code, offset)
            if following is None:
                break
            offset = following.end()
            while offset < len(code) and code[offset].isspace():
                offset += 1
            offset = _annotation_args_end(code, offset)
            if offset is None:
                break
        if offset is not None and FUNCTION.match(code, offset):
            count += 1
    return count


class KotlinJunitDiscoveryPresenceContract(unittest.TestCase):
    def test_repository_kotlin_suites_all_contribute_a_test(self):
        paths = junit_suite_paths()
        self.assertTrue(paths, "Kotlin JUnit suite inventory must not disappear")
        missing = []
        for path in paths:
            self.assertTrue(path.is_file() and not path.is_symlink())
            if junit_method_count(path.read_text(encoding="utf-8")) < 1:
                missing.append(path.relative_to(ROOT).as_posix())
        self.assertEqual([], missing, "\n".join(missing))

    def test_real_junit4_annotation_counts(self):
        source = (
            "import org.junit.Test\n"
            "class Actual {\n"
            "  @Test\n"
            "  fun verifies(): Unit = Unit\n"
            "}\n"
        )
        self.assertEqual(1, junit_method_count(source))

    def test_real_junit5_and_fully_qualified_annotations(self):
        source = (
            "import org.junit.jupiter.api.Test\n"
            "@Test fun first() = Unit\n"
            "@org.junit.Test fun second() = Unit\n"
        )
        self.assertEqual(2, junit_method_count(source))

    def test_unrelated_test_annotation_does_not_count(self):
        self.assertEqual(0, junit_method_count(
            "import fake.testing.Test\n@Test fun bogus() = Unit\n"
        ))

    def test_alias_requires_the_actual_alias(self):
        source = (
            "import org.junit.Test as JUnitCase\n"
            "@Test fun notImported() = Unit\n"
            "@JUnitCase fun real() = Unit\n"
        )
        self.assertEqual(1, junit_method_count(source))

    def test_comments_and_strings_do_not_fake_a_suite(self):
        source = (
            "import org.junit.Test\n"
            "// @Test fun foo() = Unit\n"
            "/* outer @Test fun bar() = Unit /* @Test */ */\n"
            "val x = \"\"\"@Test fun raw() = Unit\"\"\"\n"
            "val y = \"@Test fun quoted() = Unit\"\n"
        )
        self.assertEqual(0, junit_method_count(source))

    def test_annotation_on_class_or_property_does_not_count(self):
        self.assertEqual(0, junit_method_count(
            "import org.junit.Test\n"
            "@Test class Empty {}\n"
            "@Test val x = 1\n"
        ))

    def test_expected_exception_argument_is_supported(self):
        self.assertEqual(1, junit_method_count(
            "import org.junit.Test\n"
            "@Test(expected = IllegalArgumentException::class)\n"
            "fun negativeCase() = Unit\n"
        ))

    def test_stacked_annotations_and_modifiers_are_supported(self):
        self.assertEqual(1, junit_method_count(
            "import org.junit.Test\n"
            "@Test\n"
            "@Suppress(\"unused\")\n"
            "internal fun deliberate() = Unit\n"
        ))

    def test_unterminated_args_do_not_forge_a_test(self):
        self.assertEqual(0, junit_method_count(
            "import org.junit.Test\n"
            "@Test(expected = IllegalArgumentException::class\n"
            "fun bogus() = Unit\n"
        ))

    def test_unannotated_helper_does_not_count(self):
        self.assertEqual(0, junit_method_count(
            "import org.junit.Test\nclass EmptyTest { fun helper() = Unit }\n"
        ))

    def test_triple_quoted_fixture_does_not_count(self):
        self.assertEqual(0, junit_method_count(
            'import org.junit.Test\nval fixture = """\n@Test fun fake() = Unit\n"""\n'
        ))

    def test_invalid_kotlin_quotes_fail_closed(self):
        with self.assertRaises(ValueError):
            junit_method_count('import org.junit.Test\nval broken = """no end')

    def test_only_watch_test_files_are_scanned(self):
        from tempfile import TemporaryDirectory
        with TemporaryDirectory() as folder:
            root = Path(folder)
            base = root / "app/src/test/kotlin/example"
            base.mkdir(parents=True)
            suite = base / "RealTest.kt"
            suite.write_text("@Test fun real() = Unit\n", encoding="utf-8")
            (base / "Helper.kt").write_text("@Test fun fixture() = Unit\n")
            other = root / "app/src/main/kotlin"
            other.mkdir(parents=True)
            (other / "NotATest.kt").write_text("@Test fun ignored() = Unit\n")
            self.assertEqual([suite], junit_suite_paths(root))


if __name__ == "__main__":
    unittest.main()
