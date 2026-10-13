"""Prevent silent replacement of Python unittest lifecycle hooks.

Python overwrites an earlier method with the same name in a class body.
Duplicate setUp/tearDown hooks can leave tests appearing green while silently
dropping essential fixture setup or cleanup. This contract checks test sources
without importing or executing them.
"""

from __future__ import annotations

import ast
from pathlib import Path
import unittest


TESTS_DIR = Path(__file__).resolve().parent
CLASS_HOOKS = frozenset({
    "setUp", "tearDown", "setUpClass", "tearDownClass",
    "asyncSetUp", "asyncTearDown",
})
MODULE_HOOKS = frozenset({"setUpModule", "tearDownModule"})


def shadowed_hooks(source: str, filename: str = "<source>") -> list[str]:
    """Report duplicated lifecycle functions in the same lexical scope."""
    tree = ast.parse(source, filename=filename)
    violations: list[str] = []

    def scan(body: list[ast.stmt], scope: str, hooks: frozenset[str]) -> None:
        seen: dict[str, int] = {}
        for node in body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if node.name in hooks:
                    if node.name in seen:
                        violations.append(
                            f"{filename}:{node.lineno}: {scope}.{node.name} "
                            f"shadows line {seen[node.name]}"
                        )
                    else:
                        seen[node.name] = node.lineno
            elif isinstance(node, ast.ClassDef):
                scan(node.body, f"{scope}.{node.name}", CLASS_HOOKS)

    scan(tree.body, "<module>", MODULE_HOOKS)
    return sorted(violations)


class PythonUnittestLifecycleShadowingContract(unittest.TestCase):
    def test_current_python_contract_tree_has_no_shadowed_lifecycle_hooks(self):
        violations: list[str] = []
        for path in sorted(TESTS_DIR.rglob("test_*.py")):
            relative = path.relative_to(TESTS_DIR).as_posix()
            violations.extend(
                shadowed_hooks(path.read_text(encoding="utf-8"), relative)
            )
        self.assertEqual([], sorted(violations), "\n".join(violations))

    def test_repeated_setup_and_teardown_are_reported_with_both_lines(self):
        source = (
            "class Example:\n"
            "    def setUp(self): pass\n"
            "    def tearDown(self): pass\n"
            "    def setUp(self): pass\n"
            "    def tearDown(self): pass\n"
        )
        self.assertEqual(
            [
                "fixture.py:4: <module>.Example.setUp shadows line 2",
                "fixture.py:5: <module>.Example.tearDown shadows line 3",
            ],
            shadowed_hooks(source, "fixture.py"),
        )

    def test_async_and_sync_hook_collisions_are_both_detected(self):
        source = (
            "class AsyncCase:\n"
            "    async def asyncSetUp(self): pass\n"
            "    def asyncSetUp(self): pass\n"
            "    def tearDownClass(cls): pass\n"
            "    async def tearDownClass(cls): pass\n"
        )
        self.assertEqual(2, len(shadowed_hooks(source)))

    def test_separate_classes_can_use_the_same_lifecycle_hooks(self):
        source = (
            "class First:\n"
            "    def setUp(self): pass\n"
            "class Second:\n"
            "    def setUp(self): pass\n"
        )
        self.assertEqual([], shadowed_hooks(source))

    def test_nested_class_collision_is_qualified_but_parent_is_independent(self):
        source = (
            "class Parent:\n"
            "    def setUp(self): pass\n"
            "    class Child:\n"
            "        def setUp(self): pass\n"
            "        def setUp(self): pass\n"
        )
        self.assertEqual(
            ["x.py:5: <module>.Parent.Child.setUp shadows line 4"],
            shadowed_hooks(source, "x.py"),
        )

    def test_duplicate_module_setup_and_teardown_are_detected(self):
        source = (
            "def setUpModule(): pass\n"
            "def tearDownModule(): pass\n"
            "def setUpModule(): pass\n"
            "async def tearDownModule(): pass\n"
        )
        self.assertEqual(
            [
                "m.py:3: <module>.setUpModule shadows line 1",
                "m.py:4: <module>.tearDownModule shadows line 2",
            ],
            shadowed_hooks(source, "m.py"),
        )

    def test_nested_functions_do_not_create_false_positives(self):
        source = (
            "def helper():\n"
            "    def setUpModule(): pass\n"
            "    def setUpModule(): pass\n"
            "class Example:\n"
            "    def helper(self):\n"
            "        def setUp(): pass\n"
            "        def setUp(): pass\n"
        )
        self.assertEqual([], shadowed_hooks(source))

    def test_syntax_errors_fail_closed(self):
        with self.assertRaises(SyntaxError):
            shadowed_hooks("class Broken(:\n pass\n", "bad.py")
