"""Fail closed on duplicate top-level Kotlin test symbols in the same package.

A duplicate JVM test class may compile ambiguously or conceal an independent
test fixture. This check is intentionally limited to source-set top-level types,
not nested classes or Android runtime files owned by other workers.
"""
from collections import defaultdict
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]
TEST_ROOT = ROOT / "app" / "src" / "test"
PACKAGE = re.compile(r"(?m)^package\s+([A-Za-z_][\w]*(?:\.[A-Za-z_][\w]*)*)\s*$")
TYPE = re.compile(
    r"(?m)^(?:(?:public|internal|private|data|sealed|open|abstract|enum|annotation|value|expect|actual)\s+)*"
    r"(?:class|interface|object)\s+([A-Za-z_][\w]*)\b"
)


def declared_test_symbols(source: str):
    # Require one explicit package: unnamed/multi-package declarations should not
    # be accepted as a usable collision scan.
    packages = PACKAGE.findall(source)
    if len(packages) != 1:
        raise ValueError("Kotlin test source requires exactly one package")
    return {(packages[0], match) for match in TYPE.findall(source)}


def collisions(paths):
    found = defaultdict(list)
    for path in sorted(paths):
        for symbol in declared_test_symbols(path.read_text(encoding="utf-8")):
            found[symbol].append(path.as_posix())
    return {symbol: locations for symbol, locations in found.items() if len(locations) > 1}


class KotlinTestSymbolCollisionContract(unittest.TestCase):
    def test_current_test_sources_have_no_duplicate_top_level_types(self):
        paths = list(TEST_ROOT.rglob("*.kt"))
        self.assertTrue(paths, "Expected Kotlin JVM unit-test sources")
        self.assertEqual({}, collisions(paths))

    def test_duplicate_types_are_detected(self):
        source = "package nl.zennay.raiseai\nclass ExampleTest {}\n"
        self.assertEqual({("nl.zennay.raiseai", "ExampleTest")}, declared_test_symbols(source))
        self.assertEqual(set(), declared_test_symbols("package nl.zennay.raiseai\n"))

    def test_package_is_part_of_symbol_identity(self):
        self.assertNotEqual(
            declared_test_symbols("package a.b\nclass ExampleTest {}\n"),
            declared_test_symbols("package a.c\nclass ExampleTest {}\n"),
        )

    def test_missing_or_ambiguous_package_fails_closed(self):
        for source in ("class ExampleTest {}", "package a\npackage b\nclass ExampleTest {}"):
            with self.assertRaises(ValueError):
                declared_test_symbols(source)


if __name__ == "__main__":
    unittest.main()
