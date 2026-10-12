"""Prevent silently green, unawaited async unittest tests.

Ordinary unittest.TestCase does not await coroutine test methods. Python can
report them as successful even though assertions in the coroutine never run.
This static quality guard rejects that shape and accepts IsolatedAsyncioTestCase.
"""
from __future__ import annotations

import ast
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
TESTS = ROOT / "tests"


def unawaited_test_coroutines(source: str) -> list[tuple[int, str]]:
    """Find coroutine tests lacking a recognized asyncio-aware runner.

    This is conservative, static source validation, not a runtime guarantee.
    Only Python unittest source modules and local TestCase inheritance are
    interpreted; string fixtures and nested helper functions are ignored.
    """
    tree = ast.parse(source)
    unittest_modules = {"unittest"}
    sync_aliases = {"TestCase"}
    async_aliases = {"IsolatedAsyncioTestCase"}
    classes: dict[str, ast.ClassDef] = {}
    violations: list[tuple[int, str]] = []

    for statement in tree.body:
        if isinstance(statement, ast.Import):
            for alias in statement.names:
                if alias.name == "unittest":
                    unittest_modules.add(alias.asname or "unittest")
        elif isinstance(statement, ast.ImportFrom) and statement.module == "unittest":
            for alias in statement.names:
                if alias.name == "TestCase":
                    sync_aliases.add(alias.asname or alias.name)
                elif alias.name == "IsolatedAsyncioTestCase":
                    async_aliases.add(alias.asname or alias.name)
        elif isinstance(statement, ast.ClassDef):
            classes[statement.name] = statement
        elif (
            isinstance(statement, ast.AsyncFunctionDef)
            and statement.name.startswith("test_")
        ):
            # unittest never collects module-level async test functions.
            violations.append((statement.lineno, f"<module>.{statement.name}"))

    def recognized_base(base: ast.expr, visiting: frozenset[str]) -> str | None:
        if isinstance(base, ast.Attribute):
            if isinstance(base.value, ast.Name) and base.value.id in unittest_modules:
                if base.attr == "IsolatedAsyncioTestCase":
                    return "async"
                if base.attr == "TestCase":
                    return "sync"
            return None
        if not isinstance(base, ast.Name):
            return None
        if base.id in async_aliases:
            return "async"
        if base.id in sync_aliases:
            return "sync"
        if base.id not in classes or base.id in visiting:
            return None
        return class_runner(classes[base.id], visiting | {base.id})

    def class_runner(cls: ast.ClassDef, visiting: frozenset[str]) -> str | None:
        # Left-to-right is important. TestCase before IsolatedAsyncioTestCase
        # must never be considered an async-aware runner.
        for base in cls.bases:
            kind = recognized_base(base, visiting)
            if kind is not None:
                return kind
        return None

    def method_defs(cls: ast.ClassDef) -> dict[str, ast.FunctionDef | ast.AsyncFunctionDef]:
        return {
            entry.name: entry
            for entry in cls.body
            if isinstance(entry, (ast.FunctionDef, ast.AsyncFunctionDef))
            and entry.name.startswith("test_")
        }

    def effective_methods(cls: ast.ClassDef, seen: frozenset[str]):
        """Gather locally inherited test methods, with child overrides first."""
        methods = method_defs(cls)
        for base in cls.bases:
            if not isinstance(base, ast.Name):
                continue
            if base.id in classes and base.id not in seen:
                inherited = effective_methods(classes[base.id], seen | {base.id})
                for name, method in inherited.items():
                    methods.setdefault(name, method)
        return methods

    for name, cls in classes.items():
        if class_runner(cls, frozenset({name})) != "sync":
            continue
        for method_name, method in effective_methods(cls, frozenset({name})).items():
            if isinstance(method, ast.AsyncFunctionDef):
                violations.append((method.lineno, f"{name}.{method_name}"))
    return sorted(set(violations))


class UnawaitedUnittestCoroutinesContract(unittest.TestCase):
    def test_repository_has_no_unawaited_coroutine_tests(self):
        paths = sorted(TESTS.rglob("test_*.py"))
        self.assertTrue(paths, "Python quality suite cannot be empty")
        issues = []
        for path in paths:
            for line, name in unawaited_test_coroutines(path.read_text(encoding="utf-8")):
                issues.append(f"{path.relative_to(ROOT)}:{line}: {name}")
        self.assertEqual([], issues, "\n".join(issues))

    def test_plain_testcase_async_method_is_rejected(self):
        source = (
            "import unittest\n"
            "class Case(unittest.TestCase):\n"
            "    async def test_wrong(self):\n"
            "        assert False\n"
        )
        self.assertEqual(
            [(3, "Case.test_wrong")],
            unawaited_test_coroutines(source),
        )

    def test_unittest_module_alias_is_resolved(self):
        source = (
            "import unittest as ut\n"
            "class Case(ut.TestCase):\n"
            "    async def test_wrong(self): pass\n"
        )
        self.assertEqual(
            [(3, "Case.test_wrong")],
            unawaited_test_coroutines(source),
        )

    def test_direct_testcase_import_alias_is_resolved(self):
        source = (
            "from unittest import TestCase as Base\n"
            "class Case(Base):\n"
            "    async def test_wrong(self): pass\n"
        )
        self.assertEqual([(3, "Case.test_wrong")], unawaited_test_coroutines(source))

    def test_isolated_asyncio_testcase_can_await_async_methods(self):
        for source in (
            "import unittest\nclass C(unittest.IsolatedAsyncioTestCase):\n"
            "    async def test_ok(self): pass\n",
            "from unittest import IsolatedAsyncioTestCase as AsyncCase\n"
            "class C(AsyncCase):\n"
            "    async def test_ok(self): pass\n",
        ):
            with self.subTest(source=source):
                self.assertEqual([], unawaited_test_coroutines(source))

    def test_inherited_testcase_runner_is_recognized(self):
        source = (
            "from unittest import TestCase\n"
            "class Parent(TestCase): pass\n"
            "class Child(Parent):\n"
            "    async def test_bad(self): pass\n"
        )
        self.assertEqual(
            [(4, "Child.test_bad")],
            unawaited_test_coroutines(source),
        )

    def test_inherited_isolated_async_runner_is_preserved(self):
        source = (
            "from unittest import IsolatedAsyncioTestCase\n"
            "class Parent(IsolatedAsyncioTestCase): pass\n"
            "class Child(Parent):\n"
            "    async def test_good(self): pass\n"
        )
        self.assertEqual([], unawaited_test_coroutines(source))

    def test_async_methods_in_mixin_inherited_by_testcase_are_rejected(self):
        source = (
            "import unittest\n"
            "class Mixin:\n"
            "    async def test_bad(self): pass\n"
            "class Tests(Mixin, unittest.TestCase): pass\n"
        )
        self.assertEqual([(3, "Tests.test_bad")], unawaited_test_coroutines(source))

    def test_overridden_sync_method_is_not_misclassified(self):
        source = (
            "import unittest\n"
            "class Mixin:\n"
            "    async def test_helper(self): pass\n"
            "class Tests(Mixin, unittest.TestCase):\n"
            "    def test_helper(self): self.assertTrue(True)\n"
        )
        self.assertEqual([], unawaited_test_coroutines(source))

    def test_unittest_sync_runner_precedes_async_runner(self):
        source = (
            "import unittest\n"
            "class Bad(unittest.TestCase, unittest.IsolatedAsyncioTestCase):\n"
            "    async def test_wrong(self): pass\n"
        )
        self.assertEqual(
            [(3, "Bad.test_wrong")],
            unawaited_test_coroutines(source),
        )

    def test_module_async_test_is_never_discovered_by_unittest(self):
        source = "async def test_uncollected():\n    assert False\n"
        self.assertEqual(
            [(1, "<module>.test_uncollected")],
            unawaited_test_coroutines(source),
        )

    def test_regular_unittest_and_helpers_remain_allowed(self):
        source = (
            "import unittest\n"
            "class Tests(unittest.TestCase):\n"
            "    async def helper(self): pass\n"
            "    def test_real(self): self.assertTrue(True)\n"
            "def helper():\n"
            "    async def test_fixture(): pass\n"
        )
        self.assertEqual([], unawaited_test_coroutines(source))

    def test_literal_fixtures_do_not_create_false_positives(self):
        source = (
            "fixture = '''\n"
            "class Hidden(unittest.TestCase):\n"
            "    async def test_fake(self): pass\n"
            "'''\n"
        )
        self.assertEqual([], unawaited_test_coroutines(source))

    def test_syntax_errors_fail_closed(self):
        with self.assertRaises(SyntaxError):
            unawaited_test_coroutines("class Bad(:\n    pass\n")


if __name__ == "__main__":
    unittest.main()
