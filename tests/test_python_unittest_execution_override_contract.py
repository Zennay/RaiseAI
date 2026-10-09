"""Guard unittest execution hooks from silently bypassing Raise AI QA tests.

Python's unittest loader can count test methods while an overriding TestCase.run()
reports success without invoking them. Existing count/skip checks cannot prove the
test body ran in that case. Scan repository test sources without executing fixtures.
These are offline quality contracts, not physical Galaxy Watch acceptance evidence.
"""

from __future__ import annotations

import ast
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
TESTS = ROOT / "tests"
EXECUTION_HOOKS = frozenset({
    "run", "debug", "_callTestMethod", "_callSetUp", "_callTearDown",
    "_callCleanup", "doCleanups",
})


def _bound_names(target: ast.AST) -> set[str]:
    if isinstance(target, ast.Name):
        return {target.id}
    if isinstance(target, (ast.Tuple, ast.List)):
        return set().union(*(_bound_names(item) for item in target.elts))
    if isinstance(target, ast.Starred):
        return _bound_names(target.value)
    return set()


def _statements_in_scope(body: list[ast.stmt]):
    """Yield statements, including conditional blocks, but never inner scopes."""
    for statement in body:
        yield statement
        if isinstance(statement, (ast.If, ast.While, ast.For, ast.AsyncFor)):
            yield from _statements_in_scope(statement.body)
            yield from _statements_in_scope(statement.orelse)
        elif isinstance(statement, (ast.With, ast.AsyncWith)):
            yield from _statements_in_scope(statement.body)
        elif isinstance(statement, (ast.Try, getattr(ast, "TryStar", ast.Try))):
            yield from _statements_in_scope(statement.body)
            for handler in statement.handlers:
                yield handler
                yield from _statements_in_scope(handler.body)
            yield from _statements_in_scope(statement.orelse)
            yield from _statements_in_scope(statement.finalbody)
        elif isinstance(statement, ast.Match):
            for case in statement.cases:
                yield from _statements_in_scope(case.body)


def _bound_hooks(statement: ast.stmt) -> set[str]:
    if isinstance(statement, (ast.FunctionDef, ast.AsyncFunctionDef)):
        return {statement.name} & EXECUTION_HOOKS
    if isinstance(statement, (ast.Assign, ast.AnnAssign, ast.AugAssign, ast.Delete)):
        targets = (
            statement.targets
            if isinstance(statement, (ast.Assign, ast.Delete))
            else [statement.target]
        )
        names = set().union(*(_bound_names(target) for target in targets))
        return names & EXECUTION_HOOKS
    if isinstance(statement, (ast.For, ast.AsyncFor)):
        return _bound_names(statement.target) & EXECUTION_HOOKS
    if isinstance(statement, (ast.With, ast.AsyncWith)):
        return set().union(*(
            _bound_names(item.optional_vars)
            for item in statement.items if item.optional_vars is not None
        )) & EXECUTION_HOOKS
    if isinstance(statement, ast.ExceptHandler):
        return ({statement.name} if statement.name else set()) & EXECUTION_HOOKS
    if isinstance(statement, (ast.Import, ast.ImportFrom)):
        return {
            alias.asname or alias.name.split(".")[0]
            for alias in statement.names
        } & EXECUTION_HOOKS
    return set()


def _module_hook_rebindings(
    body: list[ast.stmt], descendants: set[str],
) -> list[tuple[int, str]]:
    """Catch reassignment of TestCase hooks after the class statement.

    Module-scope monkeypatching can bypass even an otherwise clean test class.
    Inner function bodies are deliberately not interpreted as executed code.
    """
    violations: list[tuple[int, str]] = []

    def hook_attribute(target: ast.AST) -> str | None:
        if (
            isinstance(target, ast.Attribute)
            and target.attr in EXECUTION_HOOKS
            and isinstance(target.value, ast.Name)
            and target.value.id in descendants
        ):
            return f"{target.value.id}.{target.attr}"
        return None

    for stmt in _statements_in_scope(body):
        targets: list[ast.expr] = []
        if isinstance(stmt, (ast.Assign, ast.Delete)):
            targets.extend(stmt.targets)
        elif isinstance(stmt, (ast.AnnAssign, ast.AugAssign)):
            targets.append(stmt.target)
        elif isinstance(stmt, (ast.For, ast.AsyncFor)):
            targets.append(stmt.target)
        elif isinstance(stmt, (ast.With, ast.AsyncWith)):
            targets.extend(
                item.optional_vars for item in stmt.items
                if item.optional_vars is not None
            )
        for target in targets:
            for node in ast.walk(target):
                name = hook_attribute(node)
                if name is not None:
                    violations.append((stmt.lineno, name))

        if (
            isinstance(stmt, ast.Expr)
            and isinstance(stmt.value, ast.Call)
            and isinstance(stmt.value.func, ast.Name)
            and stmt.value.func.id == "setattr"
            and len(stmt.value.args) >= 3
            and isinstance(stmt.value.args[0], ast.Name)
            and stmt.value.args[0].id in descendants
            and isinstance(stmt.value.args[1], ast.Constant)
            and stmt.value.args[1].value in EXECUTION_HOOKS
        ):
            violations.append((
                stmt.lineno,
                f"{stmt.value.args[0].id}.{stmt.value.args[1].value}",
            ))
    return violations


def overridden_test_execution_hooks(source: str) -> list[tuple[int, str]]:
    """Find unsafe TestCase execution-hook bindings, including local subclasses."""
    tree = ast.parse(source)
    unittest_modules = {"unittest"}
    testcase_names = {"TestCase"}
    classes: dict[str, ast.ClassDef] = {}
    for statement in _statements_in_scope(tree.body):
        if isinstance(statement, ast.Import):
            for alias in statement.names:
                if alias.name == "unittest":
                    unittest_modules.add(alias.asname or "unittest")
        elif isinstance(statement, ast.ImportFrom) and statement.module == "unittest":
            for alias in statement.names:
                if alias.name == "TestCase":
                    testcase_names.add(alias.asname or alias.name)
        elif isinstance(statement, ast.ClassDef):
            classes[statement.name] = statement

    def base_name(base: ast.expr) -> str | None:
        if isinstance(base, ast.Name):
            return base.id
        if (isinstance(base, ast.Attribute) and base.attr == "TestCase"
                and isinstance(base.value, ast.Name)
                and base.value.id in unittest_modules):
            return "TestCase"
        return None

    descendants = set(testcase_names)
    changed = True
    while changed:
        changed = False
        for name, cls in classes.items():
            if name not in descendants and any(
                base_name(base) in descendants for base in cls.bases
            ):
                descendants.add(name)
                changed = True

    violations: list[tuple[int, str]] = []
    for name, cls in classes.items():
        if name not in descendants:
            continue
        for statement in _statements_in_scope(cls.body):
            for hook in _bound_hooks(statement):
                violations.append((statement.lineno, f"{name}.{hook}"))
    violations.extend(_module_hook_rebindings(tree.body, descendants))
    return sorted(set(violations))


class PythonUnittestExecutionOverrideContract(unittest.TestCase):
    def test_repository_never_replaces_testcase_execution_hooks(self):
        paths = sorted(TESTS.rglob("test_*.py"))
        self.assertTrue(paths, "quality test inventory must not be empty")
        violations = [
            f"{path.relative_to(ROOT)}:{line}: {name}"
            for path in paths
            for line, name in overridden_test_execution_hooks(
                path.read_text(encoding="utf-8")
            )
        ]
        self.assertEqual([], violations, "\n".join(violations))

    def test_run_and_internal_dispatch_overrides_are_detected(self):
        source = (
            "import unittest\n"
            "class Silenced(unittest.TestCase):\n"
            "    def run(self, result=None): return result\n"
            "    async def _callTestMethod(self, method): pass\n"
            "    def test_other(self): pass\n"
        )
        self.assertEqual(
            [(3, "Silenced.run"), (4, "Silenced._callTestMethod")],
            overridden_test_execution_hooks(source),
        )

    def test_aliases_and_inherited_testcase_classes_are_detected(self):
        source = (
            "import unittest as ut\n"
            "from unittest import TestCase as Case\n"
            "class Base(ut.TestCase): pass\n"
            "class Child(Base):\n"
            "    def debug(self): pass\n"
            "class Second(Case):\n"
            "    def _callSetUp(self): pass\n"
        )
        self.assertEqual(
            [(5, "Child.debug"), (7, "Second._callSetUp")],
            overridden_test_execution_hooks(source),
        )

    def test_class_binding_forms_cannot_mask_hooks(self):
        source = (
            "from unittest import TestCase\n"
            "class Hidden(TestCase):\n"
            "    run = lambda self, result: result\n"
            "    debug: object\n"
            "    for doCleanups in []: pass\n"
            "    if True:\n"
            "        from helpers import fake as _callCleanup\n"
            "    try: pass\n"
            "    except Exception as _callTearDown: pass\n"
        )
        self.assertEqual(
            [
                (3, "Hidden.run"),
                (4, "Hidden.debug"),
                (5, "Hidden.doCleanups"),
                (7, "Hidden._callCleanup"),
                (9, "Hidden._callTearDown"),
            ],
            overridden_test_execution_hooks(source),
        )

    def test_unrelated_helpers_and_nested_functions_are_not_reported(self):
        source = (
            "import unittest\n"
            "class Runner:\n"
            "    def run(self): pass\n"
            "class Safe(unittest.TestCase):\n"
            "    def test_example(self):\n"
            "        def run(): pass\n"
            "        self.run = None\n"
            "    def helper(self):\n"
            "        def _callTestMethod(): pass\n"
            "fixture = 'class Test(unittest.TestCase): def run(self): pass'\n"
        )
        self.assertEqual([], overridden_test_execution_hooks(source))

    def test_post_definition_testcase_monkeypatching_is_rejected(self):
        source = (
            "import unittest\\n"
            "class Hidden(unittest.TestCase):\\n"
            "    def test_real(self): pass\\n"
            "Hidden.run = lambda self, result: result\\n"
            "setattr(Hidden, '_callTestMethod', lambda self, method: None)\\n"
            "if True:\\n"
            "    Hidden.debug = lambda self: None\\n"
        )
        self.assertEqual(
            [(4, "Hidden.run"), (5, "Hidden._callTestMethod"),
             (7, "Hidden.debug")],
            overridden_test_execution_hooks(source),
        )

    def test_unrelated_module_hooks_and_function_locals_are_allowed(self):
        source = (
            "import unittest\\n"
            "class Helper:\\n"
            "    def run(self): pass\\n"
            "class Safe(unittest.TestCase):\\n"
            "    def test_live(self): pass\\n"
            "Helper.run = 3\\n"
            "def factory():\\n"
            "    Safe.run = 5\\n"
            "    setattr(Safe, 'debug', lambda self: None)\\n"
        )
        self.assertEqual([], overridden_test_execution_hooks(source))

    def test_regular_testcase_methods_remain_allowed(self):
        source = (
            "from unittest import TestCase\n"
            "class Genuine(TestCase):\n"
            "    def setUp(self): self.ready = True\n"
            "    def tearDown(self): pass\n"
            "    def test_actual(self): self.assertTrue(self.ready)\n"
        )
        self.assertEqual([], overridden_test_execution_hooks(source))


if __name__ == "__main__":
    unittest.main()
