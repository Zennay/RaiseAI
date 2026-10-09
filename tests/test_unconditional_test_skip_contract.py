"""Fail closed on unconditional unittest skips that silently erase coverage.

This is a static quality guard, not evidence of a physical Galaxy Watch run.
Platform-conditional skips remain permitted; unconditionally disabled tests do not.
"""

import ast
import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
DISABLING_DECORATORS = {"skip", "expectedFailure"}


def disabled_tests(source: str) -> list[tuple[int, str]]:
    """Return (line, name) for statically disabled test definitions."""
    tree = ast.parse(source)
    module_names = {"unittest"}
    direct_names = {}
    case_names = {"TestCase"}
    for statement in tree.body:
        if isinstance(statement, ast.Import):
            for alias in statement.names:
                if alias.name == "unittest":
                    module_names.add(alias.asname or "unittest")
        elif isinstance(statement, ast.ImportFrom) and statement.module == "unittest":
            for alias in statement.names:
                local = alias.asname or alias.name
                if alias.name in DISABLING_DECORATORS | {"skipIf", "skipUnless"}:
                    direct_names[local] = alias.name
                if alias.name == "TestCase":
                    case_names.add(local)

    def decorator_kind(decorator):
        condition = None
        call = isinstance(decorator, ast.Call)
        function = decorator.func if call else decorator
        name = None
        if isinstance(function, ast.Name):
            name = direct_names.get(function.id)
        elif (
            isinstance(function, ast.Attribute)
            and isinstance(function.value, ast.Name)
            and function.value.id in module_names
        ):
            name = function.attr
        if name in DISABLING_DECORATORS:
            return name
        if call:
            condition_node = (
                decorator.args[0] if decorator.args
                else next(
                    (keyword.value for keyword in decorator.keywords
                     if keyword.arg == "condition"),
                    None,
                )
            )
            if isinstance(condition_node, ast.Constant):
                condition = condition_node.value
                if type(condition) is bool:
                    if name == "skipIf" and condition is True:
                        return name
                    if name == "skipUnless" and condition is False:
                        return name
        return None

    def test_class(node):
        if node.name.startswith("Test"):
            return True
        for base in node.bases:
            if isinstance(base, ast.Name) and base.id in case_names:
                return True
            if (
                isinstance(base, ast.Attribute)
                and isinstance(base.value, ast.Name)
                and base.value.id in module_names
                and base.attr == "TestCase"
            ):
                return True
        return False

    disabled = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            eligible = node.name.startswith("test_")
        elif isinstance(node, ast.ClassDef):
            eligible = test_class(node)
        else:
            continue
        if not eligible:
            continue
        for decorator in node.decorator_list:
            kind = decorator_kind(decorator)
            if kind:
                disabled.append((node.lineno, f"{node.name}: {kind}"))
    return sorted(set(disabled))


class UnconditionalTestSkipContract(unittest.TestCase):
    def test_repository_test_tree_has_no_unconditionally_disabled_tests(self):
        paths = sorted((ROOT / "tests").rglob("test_*.py"))
        self.assertTrue(paths, "test discovery must not silently become empty")
        violations = []
        for path in paths:
            for line, name in disabled_tests(path.read_text(encoding="utf-8")):
                violations.append(f"{path.relative_to(ROOT)}:{line}: {name}")
        self.assertEqual(violations, [], "\n".join(violations))

    def test_direct_and_aliased_unconditional_skip_are_detected(self):
        source = """import unittest as ut
from unittest import skip as bypass
class TestExample(ut.TestCase):
    @ut.skip('off')
    def test_one(self): pass
    @bypass('off')
    async def test_two(self): pass
"""
        self.assertEqual(
            disabled_tests(source),
            [(5, "test_one: skip"), (7, "test_two: skip")],
        )

    def test_expected_failure_and_class_skip_are_detected(self):
        source = """import unittest
@unittest.skip('disabled suite')
class ExampleTests(unittest.TestCase):
    @unittest.expectedFailure
    def test_hidden(self): pass
"""
        self.assertEqual(
            disabled_tests(source),
            [(3, "ExampleTests: skip"), (5, "test_hidden: expectedFailure")],
        )

    def test_literal_always_true_conditions_are_detected(self):
        source = """from unittest import skipIf, skipUnless
@skipIf(True, 'unconditional')
def test_a(): pass
@skipUnless(False, 'unconditional')
def test_b(): pass
"""
        self.assertEqual(
            disabled_tests(source),
            [(3, "test_a: skipIf"), (5, "test_b: skipUnless")],
        )

    def test_keyword_constant_conditions_cannot_bypass_guard(self):
        source = """from unittest import skipIf as if_skip, skipUnless as unless_skip
@if_skip(condition=True, reason='always skipped')
def test_one(): pass
@unless_skip(condition=False, reason='always skipped')
def test_two(): pass
"""
        self.assertEqual(
            disabled_tests(source),
            [(3, "test_one: skipIf"), (5, "test_two: skipUnless")],
        )

    def test_conditional_skips_remain_legal(self):
        source = """import os
import unittest
@unittest.skipUnless(hasattr(os, 'mkfifo'), 'unsupported platform')
def test_fifo(): pass
@unittest.skipIf(os.name == 'nt', 'unix only')
def test_unix(): pass
@unittest.skipIf(False, 'enabled')
def test_enabled(): pass
@unittest.skipUnless(True, 'enabled')
def test_also_enabled(): pass
"""
        self.assertEqual(disabled_tests(source), [])

    def test_synthetic_strings_and_unrelated_decorators_are_ignored(self):
        source = """import unittest
fixture = '''
@unittest.skip('disabled')
def test_fixture(): pass
'''
class Other:
    def skip(self, why): return lambda fn: fn
other = Other()
@other.skip('not unittest')
def test_live(): pass
@unittest.skip('helper is not a test')
def helper(): pass
"""
        self.assertEqual(disabled_tests(source), [])


if __name__ == "__main__":
    unittest.main()
