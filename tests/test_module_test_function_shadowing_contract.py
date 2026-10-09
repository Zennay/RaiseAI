"""Ensure module-level Python test definitions are not silently overwritten."""
import ast
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]

def duplicate_module_tests(source):
    seen = set()
    duplicates = set()
    for node in ast.parse(source).body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("test_"):
            if node.name in seen:
                duplicates.add(node.name)
            seen.add(node.name)
    return sorted(duplicates)

class ModuleTestFunctionShadowingContract(unittest.TestCase):
    def test_repository_modules(self):
        offenders = {}
        for path in sorted((ROOT / "tests").rglob("test_*.py")):
            duplicates = duplicate_module_tests(path.read_text(encoding="utf-8"))
            if duplicates:
                offenders[str(path.relative_to(ROOT))] = duplicates
        self.assertEqual(offenders, {})

    def test_duplicate_sync_functions(self):
        self.assertEqual(duplicate_module_tests("def test_a(): pass\ndef test_a(): pass\n"), ["test_a"])

    def test_duplicate_async_sync_functions(self):
        self.assertEqual(duplicate_module_tests("async def test_z(): pass\ndef test_z(): pass\n"), ["test_z"])

    def test_nested_functions_do_not_collide(self):
        source = "def test_x():\n    def test_x(): pass\nclass T:\n    def test_x(self): pass\n"
        self.assertEqual(duplicate_module_tests(source), [])

    def test_distinct_names_are_valid(self):
        self.assertEqual(duplicate_module_tests("def test_a(): pass\ndef test_b(): pass\n"), [])

    def test_duplicates_report_in_stable_order(self):
        source = "def test_z(): pass\ndef test_a(): pass\ndef test_z(): pass\nasync def test_a(): pass\n"
        self.assertEqual(duplicate_module_tests(source), ["test_a", "test_z"])

if __name__ == "__main__":
    unittest.main()
