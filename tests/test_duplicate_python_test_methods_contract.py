"""Prevent duplicate Python unittest method names from silently replacing tests.

Python class construction keeps only the last definition with a given name.
This independent regression scans source AST instead of importing test modules.
"""
import ast
from pathlib import Path
import tempfile
import unittest


def duplicate_test_methods(source: str) -> tuple[str, ...]:
    tree = ast.parse(source)
    duplicates = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue
        seen = set()
        for member in node.body:
            if not isinstance(member, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if not member.name.startswith("test_"):
                continue
            if member.name in seen:
                duplicates.append(f"{node.name}.{member.name}")
            seen.add(member.name)
    return tuple(sorted(duplicates))


class DuplicatePythonTestMethodsContract(unittest.TestCase):
    def test_repository_test_classes_have_no_overwritten_test_methods(self):
        tests = Path(__file__).resolve().parent
        problems = {}
        for path in sorted(tests.rglob("test_*.py")):
            if path.is_symlink() or not path.is_file():
                continue
            found = duplicate_test_methods(path.read_text(encoding="utf-8"))
            if found:
                problems[path.relative_to(tests).as_posix()] = found
        self.assertEqual(problems, {}, "Duplicate test methods silently overwrite earlier tests")

    def test_duplicate_methods_in_same_class_are_rejected(self):
        source = "class Sample:\n    def test_repeat(self): pass\n    def test_repeat(self): pass\n"
        self.assertEqual(duplicate_test_methods(source), ("Sample.test_repeat",))

    def test_same_test_name_in_different_classes_is_valid(self):
        source = ("class Alpha:\n    def test_ok(self): pass\n"
                  "class Beta:\n    def test_ok(self): pass\n")
        self.assertEqual(duplicate_test_methods(source), ())

    def test_sync_and_async_duplicates_are_rejected(self):
        source = ("class Sample:\n    async def test_repeat(self): pass\n"
                  "    def test_repeat(self): pass\n")
        self.assertEqual(duplicate_test_methods(source), ("Sample.test_repeat",))

    def test_nested_classes_are_checked_independently(self):
        source = ("class Outer:\n    class Inner:\n"
                  "        def test_x(self): pass\n"
                  "        def test_x(self): pass\n")
        self.assertEqual(duplicate_test_methods(source), ("Inner.test_x",))


if __name__ == "__main__":
    unittest.main()
