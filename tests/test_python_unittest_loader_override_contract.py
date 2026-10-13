"""Prevent unittest's load_tests protocol from silently filtering quality coverage.

The all-Python contract runner verifies that each module contributes at least one
test, but a module-level load_tests override could still selectively hide tests
within that module. Keep discovery controlled by the shared runner.
"""

import ast
from pathlib import Path
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


def quality_contract_paths(root: Path = ROOT) -> list[Path]:
    """Scan test modules AND package initializers; both can define load_tests."""
    tests = root / "tests"
    return sorted(set(tests.rglob("test_*.py")) | set(tests.rglob("__init__.py")))


def _binds_name(target: ast.AST, name: str) -> bool:
    if isinstance(target, ast.Name):
        return target.id == name
    if isinstance(target, (ast.Tuple, ast.List)):
        return any(_binds_name(element, name) for element in target.elts)
    if isinstance(target, ast.Starred):
        return _binds_name(target.value, name)
    return False


def module_loader_overrides(source: str) -> list[tuple[int, str]]:
    """Find module-scope definitions/bindings of unittest's load_tests hook."""
    tree = ast.parse(source)
    found: list[tuple[int, str]] = []

    def inspect(statements: list[ast.stmt]) -> None:
        for statement in statements:
            if isinstance(statement, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if statement.name == "load_tests":
                    found.append((statement.lineno, "function"))
                # Nested functions/classes are separate Python scopes.
                continue
            if isinstance(statement, ast.ClassDef):
                continue
            if isinstance(statement, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
                targets = (
                    statement.targets if isinstance(statement, ast.Assign)
                    else [statement.target]
                )
                if any(_binds_name(target, "load_tests") for target in targets):
                    found.append((statement.lineno, "assignment"))
            elif isinstance(statement, (ast.Import, ast.ImportFrom)):
                for alias in statement.names:
                    if (alias.asname or alias.name.split(".")[0]) == "load_tests":
                        found.append((statement.lineno, "import"))
            elif isinstance(statement, (ast.For, ast.AsyncFor)):
                if _binds_name(statement.target, "load_tests"):
                    found.append((statement.lineno, "loop target"))
            elif isinstance(statement, (ast.With, ast.AsyncWith)):
                if any(
                    item.optional_vars is not None
                    and _binds_name(item.optional_vars, "load_tests")
                    for item in statement.items
                ):
                    found.append((statement.lineno, "with target"))
            elif isinstance(statement, ast.Try):
                for handler in statement.handlers:
                    if handler.name == "load_tests":
                        found.append((handler.lineno, "except target"))

            # Module-scope control flow preserves module scope. Do not walk
            # expression trees or inner function/class bodies.
            if isinstance(statement, (ast.If, ast.While, ast.For, ast.AsyncFor)):
                inspect(statement.body)
                inspect(statement.orelse)
            elif isinstance(statement, (ast.Try, getattr(ast, "TryStar", ast.Try))):
                inspect(statement.body)
                for handler in statement.handlers:
                    inspect(handler.body)
                inspect(statement.orelse)
                inspect(statement.finalbody)
            elif isinstance(statement, (ast.With, ast.AsyncWith)):
                inspect(statement.body)
            elif isinstance(statement, ast.Match):
                for case in statement.cases:
                    inspect(case.body)

    inspect(tree.body)
    return sorted(set(found))


class PythonUnittestLoaderOverrideContractTests(unittest.TestCase):
    def test_repo_does_not_override_unittest_discovery_hooks(self):
        paths = quality_contract_paths()
        self.assertTrue(paths, "Python quality suite must not become empty")
        violations = [
            f"{path.relative_to(ROOT)}:{line}: {kind}"
            for path in paths
            for line, kind in module_loader_overrides(path.read_text(encoding="utf-8"))
        ]
        self.assertEqual(violations, [], "\n".join(violations))

    def test_discovery_guard_includes_package_initializers(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            package = root / "tests"
            nested = package / "nested"
            nested.mkdir(parents=True)
            (package / "__init__.py").write_text("def load_tests(*args): return []\n")
            (nested / "__init__.py").write_text("def load_tests(*args): return []\n")
            (nested / "test_sample.py").write_text("def test_real(): pass\n")
            paths = quality_contract_paths(root)
            self.assertEqual(
                [path.relative_to(root).as_posix() for path in paths],
                ["tests/__init__.py", "tests/nested/__init__.py", "tests/nested/test_sample.py"],
            )
            self.assertEqual(
                [path.relative_to(root).as_posix() for path in paths
                 if module_loader_overrides(path.read_text(encoding="utf-8"))],
                ["tests/__init__.py", "tests/nested/__init__.py"],
            )

    def test_module_function_and_async_function_are_rejected(self):
        self.assertEqual(
            module_loader_overrides(
                "def load_tests(loader, tests, pattern):\n    return tests\n"
                "async def load_tests(loader, tests, pattern):\n    return tests\n"
            ),
            [(1, "function"), (3, "function")],
        )

    def test_alias_and_destructuring_assignment_are_rejected(self):
        self.assertEqual(
            module_loader_overrides(
                "load_tests = lambda loader, tests, pattern: tests\n"
                "(other, load_tests) = (1, 2)\n"
                "load_tests: object\n"
            ),
            [(1, "assignment"), (2, "assignment"), (3, "assignment")],
        )

    def test_conditional_and_exception_handlers_are_not_bypasses(self):
        source = (
            "if True:\n"
            "    def load_tests(loader, tests, pattern): return tests\n"
            "try:\n"
            "    pass\n"
            "except ValueError as load_tests:\n"
            "    pass\n"
        )
        self.assertEqual(
            module_loader_overrides(source),
            [(2, "function"), (5, "except target")],
        )

    def test_import_and_loop_bindings_are_rejected(self):
        source = (
            "from module import helper as load_tests\n"
            "import tests as load_tests\n"
            "for load_tests in range(3):\n"
            "    pass\n"
        )
        self.assertEqual(
            module_loader_overrides(source),
            [(1, "import"), (2, "import"), (3, "loop target")],
        )

    def test_with_target_is_rejected(self):
        source = "with open('file') as load_tests:\n    pass\n"
        self.assertEqual(module_loader_overrides(source), [(1, "with target")])

    def test_class_methods_and_nested_functions_are_not_module_overrides(self):
        source = (
            "class TestFixture:\n"
            "    def load_tests(self):\n"
            "        return []\n"
            "def helper():\n"
            "    def load_tests(): return []\n"
            "    return load_tests\n"
        )
        self.assertEqual(module_loader_overrides(source), [])

    def test_regular_python_tests_are_allowed(self):
        source = (
            "import unittest\n"
            "from unittest import TestCase\n"
            "class SampleTests(TestCase):\n"
            "    def test_real(self): pass\n"
        )
        self.assertEqual(module_loader_overrides(source), [])


if __name__ == "__main__":
    unittest.main()
