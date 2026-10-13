"""Keep Android/Kotlin JUnit coverage from being silently disabled.

Python unittest skip guards do not inspect Kotlin sources. This check scans
Kotlin unit/instrumentation test files without compiling or executing them.
It never claims to substitute for JVM/Watch CI or physical-device acceptance.
"""
from __future__ import annotations

from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]
KOTLIN_TEST_ROOTS = (ROOT / "app/src/test", ROOT / "app/src/androidTest")
DISABLED_JUNIT = frozenset({"org.junit.Ignore", "org.junit.jupiter.api.Disabled"})
ANNOTATION = re.compile(
    r"@(?:[A-Za-z_][A-Za-z_0-9]*:)?"
    r"([A-Za-z_][A-Za-z_0-9]*(?:\.[A-Za-z_][A-Za-z_0-9]*)*)"
)
JUNIT_IMPORT = re.compile(
    r"(?m)^[ \t]*import[ \t]+"
    r"(org\.junit\.Ignore|org\.junit\.jupiter\.api\.Disabled)"
    r"(?:[ \t]+as[ \t]+([A-Za-z_][A-Za-z_0-9]*))?[ \t]*$"
)
JUNIT_TYPEALIAS = re.compile(
    r"(?m)^[ \t]*(?:public[ \t]+|internal[ \t]+|private[ \t]+)?"
    r"typealias[ \t]+([A-Za-z_][A-Za-z_0-9]*)[ \t]*="
    r"[ \t]*([A-Za-z_][A-Za-z_0-9]*(?:\.[A-Za-z_][A-Za-z_0-9]*)*)[ \t]*$"
)


def kotlin_code_only(source: str) -> str:
    """Mask comments and string/char values, preserving source line numbers.

    Kotlin supports nested block comments and triple-quoted strings. Match
    those first so quoted/fixture text cannot trigger spurious annotations.
    Fail closed on malformed quoted/comment input rather than mis-scan it.
    """
    output: list[str] = []
    index = 0
    length = len(source)

    def hidden(text: str) -> str:
        return "".join("\n" if char == "\n" else " " for char in text)

    while index < length:
        start = index
        if source.startswith("//", index):
            end = source.find("\n", index)
            index = end if end >= 0 else length
        elif source.startswith("/*", index):
            index += 2
            depth = 1
            while index < length and depth:
                if source.startswith("/*", index):
                    depth += 1
                    index += 2
                elif source.startswith("*/", index):
                    depth -= 1
                    index += 2
                else:
                    index += 1
            if depth:
                raise ValueError("unterminated Kotlin block comment")
        elif source.startswith('"""', index):
            end = source.find('"""', index + 3)
            if end < 0:
                raise ValueError("unterminated Kotlin triple-quoted string")
            index = end + 3
        elif source[index] in {'"', "'"}:
            quote = source[index]
            index += 1
            closed = False
            while index < length:
                if source[index] == "\\":
                    index += 2
                elif source[index] == quote:
                    index += 1
                    closed = True
                    break
                elif source[index] == "\n":
                    raise ValueError("unterminated Kotlin quoted literal")
                else:
                    index += 1
            if not closed:
                raise ValueError("unterminated Kotlin quoted literal")
        else:
            output.append(source[index])
            index += 1
            continue
        output.append(hidden(source[start:index]))
    return "".join(output)


def disabled_junit_annotations(source: str) -> list[tuple[int, str]]:
    """Return source lines with active JUnit @Ignore/@Disabled annotations.

    Only exact JUnit qualified names, bare conventional names, and aliases
    of real JUnit imports count. An unrelated Foo.Ignore does not.
    """
    code = kotlin_code_only(source)
    aliases = {
        match.group(2)
        for match in JUNIT_IMPORT.finditer(code)
        if match.group(2) is not None
    }
    # Annotation class typealiases are legal Kotlin and can suppress JUnit
    # tests without an @Ignore literal at the call site. Resolve transitive
    # aliases only when rooted in the two recognized JUnit disable markers.
    typealiases = [match.groups() for match in JUNIT_TYPEALIAS.finditer(code)]
    # In reverse-declared chains, only one ancestor resolves per pass. Bound
    # convergence by the number of aliases rather than an arbitrary 64 so
    # long chains never bypass an otherwise actionable @Ignore annotation.
    for _ in range(len(typealiases) + 1):
        changed = False
        for name, target in typealiases:
            if target in DISABLED_JUNIT or target in {"Ignore", "Disabled"} or target in aliases:
                if name not in aliases:
                    aliases.add(name)
                    changed = True
        if not changed:
            break

    violations: list[tuple[int, str]] = []
    for match in ANNOTATION.finditer(code):
        name = match.group(1)
        if name in DISABLED_JUNIT or name in {"Ignore", "Disabled"} or name in aliases:
            line = code.count("\n", 0, match.start()) + 1
            violations.append((line, name))
    return violations


def kotlin_test_paths(root: Path = ROOT) -> list[Path]:
    paths: list[Path] = []
    for section in ("app/src/test", "app/src/androidTest"):
        base = root / section
        if base.is_dir():
            paths.extend(base.rglob("*.kt"))
    return sorted(paths)


class KotlinJunitDisableContract(unittest.TestCase):
    def test_repository_junit_test_sources_are_not_silently_disabled(self):
        paths = kotlin_test_paths()
        self.assertTrue(paths, "Kotlin JUnit coverage must not disappear")
        violations = []
        for path in paths:
            self.assertTrue(path.is_file() and not path.is_symlink())
            for line, name in disabled_junit_annotations(path.read_text(encoding="utf-8")):
                violations.append(f"{path.relative_to(ROOT)}:{line}: @{name}")
        self.assertEqual(violations, [], "\n".join(violations))

    def test_direct_junit4_and_junit5_annotations_are_detected(self):
        source = (
            "import org.junit.Ignore\n"
            "import org.junit.jupiter.api.Disabled\n"
            "@Ignore(\"skip\")\n"
            "class TestCase {\n"
            "  @Disabled\n"
            "  fun testOne() = Unit\n"
            "}\n"
        )
        self.assertEqual(
            [(3, "Ignore"), (5, "Disabled")],
            disabled_junit_annotations(source),
        )

    def test_fully_qualified_annotations_are_detected_without_import(self):
        source = (
            "@org.junit.Ignore\n"
            "class A\n"
            "@org.junit.jupiter.api.Disabled(\"off\")\n"
            "class B\n"
        )
        self.assertEqual(
            [(1, "org.junit.Ignore"), (3, "org.junit.jupiter.api.Disabled")],
            disabled_junit_annotations(source),
        )

    def test_import_renaming_cannot_hide_disabled_tests(self):
        source = (
            "import org.junit.Ignore as Silent\n"
            "import org.junit.jupiter.api.Disabled as NoCoverage\n"
            "@Silent\n"
            "class A\n"
            "@NoCoverage\n"
            "class B\n"
        )
        self.assertEqual(
            [(3, "Silent"), (5, "NoCoverage")],
            disabled_junit_annotations(source),
        )

    def test_annotation_typealiases_cannot_bypass_junit_guard(self):
        source = (
            "import org.junit.Ignore as Hidden\n"
            "typealias First = Hidden\n"
            "internal typealias Second = First\n"
            "@Second\n"
            "class Suppressed\n"
            "typealias Third = org.junit.jupiter.api.Disabled\n"
            "@Third\n"
            "class Muted\n"
        )
        self.assertEqual(
            [(4, "Second"), (7, "Third")],
            disabled_junit_annotations(source),
        )

    def test_reverse_declared_long_alias_chain_cannot_hide_junit_disable(self):
        declarations = [
            f"typealias Alias{index} = "
            + ("org.junit.Ignore" if index == 0 else f"Alias{index - 1}")
            for index in range(72)
        ]
        source = "\n".join(reversed(declarations)) + "\n@Alias71\nclass Muted\n"
        self.assertEqual(
            [(73, "Alias71")],
            disabled_junit_annotations(source),
        )

    def test_unrelated_typealias_is_not_mistaken_for_junit_disable(self):
        source = (
            "typealias IgnoreLike = other.library.Ignore\n"
            "@IgnoreLike\n"
            "class Fixture\n"
        )
        self.assertEqual([], disabled_junit_annotations(source))

    def test_kotlin_annotation_use_site_target_is_detected(self):
        self.assertEqual(
            [(1, "Ignore")],
            disabled_junit_annotations("@get:Ignore\nval test = 1\n"),
        )

    def test_multiline_nested_comments_and_raw_strings_are_ignored(self):
        source = (
            "// @Ignore\n"
            "/* outer @Disabled\n"
            "   /* inner @org.junit.Ignore */\n"
            "*/\n"
            "val fixture = \"\"\"@Ignore\n"
            "@Disabled\"\"\"\n"
            "val quoted = \"@Ignore\"\n"
            "val char = '@'\n"
            "@Test\n"
            "fun actualTest() = Unit\n"
        )
        self.assertEqual([], disabled_junit_annotations(source))
        self.assertEqual(10, kotlin_code_only(source).count("\n"))

    def test_unrelated_annotations_and_imports_are_permitted(self):
        source = (
            "import other.library.Ignore as Other\n"
            "@other.library.Ignore\n"
            "@Other\n"
            "@org.junit.Test\n"
            "@Test(expected = IllegalArgumentException::class)\n"
            "fun realTest() = Unit\n"
        )
        self.assertEqual([], disabled_junit_annotations(source))

    def test_quoted_inline_import_is_not_authoritative(self):
        source = (
            "val fixture = \"\"\"import org.junit.Ignore as Bypass\"\"\"\n"
            "@Bypass\n"
            "fun harmless() = Unit\n"
        )
        self.assertEqual([], disabled_junit_annotations(source))

    def test_unterminated_comments_and_strings_fail_closed(self):
        for source in ("/* unfinished", 'val bad = """unfinished', 'val bad = "unfinished'):
            with self.subTest(source=source):
                with self.assertRaises(ValueError):
                    disabled_junit_annotations(source)

    def test_line_numbers_survive_masked_literals(self):
        source = 'val fake = """first\n@Ignore\nthird"""\n@Ignore\n'
        self.assertEqual([(4, "Ignore")], disabled_junit_annotations(source))

    def test_repository_scanner_ignores_non_test_kotlin_sources(self):
        from tempfile import TemporaryDirectory
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            test_dir = root / "app/src/test/java/demo"
            test_dir.mkdir(parents=True)
            test_file = test_dir / "ActualTest.kt"
            test_file.write_text("@Test fun active() = Unit\n", encoding="utf-8")
            main_dir = root / "app/src/main/java/demo"
            main_dir.mkdir(parents=True)
            (main_dir / "Ignore.kt").write_text("@Ignore\n", encoding="utf-8")
            self.assertEqual(kotlin_test_paths(root), [test_file])


if __name__ == "__main__":
    unittest.main()
