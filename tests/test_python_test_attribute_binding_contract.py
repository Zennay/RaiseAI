"""Catch class-scope rebinding that silently removes unittest test methods.

Python unittest discovers callable test_* attributes on a TestCase class.
Replacing or deleting such an attribute after its method declaration can erase a
test without failing discovery (other tests in the class may still run).

This is a static quality guard, not physical Galaxy Watch acceptance evidence.
"""

import ast
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


def _names(target: ast.AST) -> list[str]:
    if isinstance(target, ast.Name):
        return [target.id] if target.id.startswith("test_") else []
    if isinstance(target, (ast.Tuple, ast.List)):
        return [name for item in target.elts for name in _names(item)]
    if isinstance(target, ast.Starred):
        return _names(target.value)
    return []


def class_test_attribute_bindings(source: str) -> list[tuple[int, str, str]]:
    """Return (line, qualified attribute, operation) for suspicious bindings.

    Only class namespace statements count. Local variables inside functions,
    instance attributes, and module-level test fixtures are not class bindings.
    """
    tree = ast.parse(source)
    violations: list[tuple[int, str, str]] = []

    def record(node: ast.AST, path: tuple[str, ...], targets: list[ast.AST], kind: str) -> None:
        for target in targets:
            for name in _names(target):
                violations.append((node.lineno, ".".join((*path, name)), kind))

    def walk(statements: list[ast.stmt], path: tuple[str, ...]) -> None:
        for node in statements:
            if isinstance(node, ast.ClassDef):
                walk(node.body, (*path, node.name))
                continue
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                # Local variables of a test or helper are not class attributes.
                continue

            if path:
                if isinstance(node, ast.Assign):
                    record(node, path, node.targets, "assignment")
                elif isinstance(node, ast.AnnAssign) and node.value is not None:
                    record(node, path, [node.target], "annotated assignment")
                elif isinstance(node, ast.AugAssign):
                    record(node, path, [node.target], "augmented assignment")
                elif isinstance(node, ast.Delete):
                    record(node, path, node.targets, "deletion")
                elif isinstance(node, (ast.For, ast.AsyncFor)):
                    record(node, path, [node.target], "loop target")
                elif isinstance(node, (ast.With, ast.AsyncWith)):
                    record(
                        node,
                        path,
                        [item.optional_vars for item in node.items if item.optional_vars is not None],
                        "with target",
                    )
                elif isinstance(node, (ast.Import, ast.ImportFrom)):
                    for alias in node.names:
                        name = alias.asname or alias.name.split(".")[0]
                        if name.startswith("test_"):
                            violations.append((node.lineno, ".".join((*path, name)), "import"))
                elif isinstance(node, (ast.Try, getattr(ast, "TryStar", ast.Try))):
                    for handler in node.handlers:
                        if handler.name and handler.name.startswith("test_"):
                            violations.append(
                                (handler.lineno, ".".join((*path, handler.name)), "except target")
                            )

            if isinstance(node, (ast.If, ast.While, ast.For, ast.AsyncFor)):
                walk(node.body, path)
                walk(node.orelse, path)
            elif isinstance(node, (ast.With, ast.AsyncWith)):
                walk(node.body, path)
            elif isinstance(node, (ast.Try, getattr(ast, "TryStar", ast.Try))):
                walk(node.body, path)
                for handler in node.handlers:
                    walk(handler.body, path)
                walk(node.orelse, path)
                walk(node.finalbody, path)
            elif isinstance(node, ast.Match):
                for case in node.cases:
                    walk(case.body, path)

    walk(tree.body, ())
    return sorted(set(violations))


class PythonTestAttributeBindingContract(unittest.TestCase):
    def test_repository_test_classes_do_not_rebind_test_attributes(self):
        paths = sorted((ROOT / "tests").rglob("test_*.py"))
        self.assertTrue(paths, "Python quality test tree must not disappear")
        violations = [
            f"{path.relative_to(ROOT)}:{line}: {name} ({operation})"
            for path in paths
            for line, name, operation in class_test_attribute_bindings(
                path.read_text(encoding="utf-8")
            )
        ]
        self.assertEqual(violations, [], "\n".join(violations))

    def test_assignments_and_deletions_cannot_shadow_methods(self):
        source = (
            "class TestExample:\n"
            "    def test_live(self): pass\n"
            "    test_live = None\n"
            "    test_typed: object = None\n"
            "    test_increment += 1\n"
            "    (test_left, other) = (1, 2)\n"
            "    del test_deleted\n"
        )
        self.assertEqual(
            class_test_attribute_bindings(source),
            [
                (3, "TestExample.test_live", "assignment"),
                (4, "TestExample.test_typed", "annotated assignment"),
                (5, "TestExample.test_increment", "augmented assignment"),
                (6, "TestExample.test_left", "assignment"),
                (7, "TestExample.test_deleted", "deletion"),
            ],
        )

    def test_control_flow_and_import_bindings_cannot_hide_tests(self):
        source = (
            "class TestExample:\n"
            "    if True:\n"
            "        test_conditional = None\n"
            "    for test_loop in []: pass\n"
            "    with context() as test_with: pass\n"
            "    try: pass\n"
            "    except ValueError as test_error: pass\n"
            "    from package import helper as test_imported\n"
        )
        self.assertEqual(
            class_test_attribute_bindings(source),
            [
                (3, "TestExample.test_conditional", "assignment"),
                (4, "TestExample.test_loop", "loop target"),
                (5, "TestExample.test_with", "with target"),
                (7, "TestExample.test_error", "except target"),
                (8, "TestExample.test_imported", "import"),
            ],
        )

    def test_nested_class_reports_fully_qualified_attribute(self):
        source = (
            "class Outer:\n"
            "    class Inner:\n"
            "        test_missing = 0\n"
            "    def helper(self):\n"
            "        class Local:\n"
            "            test_inside_method = 0\n"
        )
        self.assertEqual(
            class_test_attribute_bindings(source),
            [(3, "Outer.Inner.test_missing", "assignment")],
        )

    def test_fixture_strings_methods_and_nonbinding_annotations_are_ignored(self):
        source = (
            "test_module_fixture = None\n"
            "class TestLive:\n"
            "    test_metadata: object\n"
            "    helper = 1\n"
            "    def test_real(self):\n"
            "        test_local = None\n"
            "        self.test_instance = None\n"
            "    fixture = 'test_fake = None'\n"
        )
        self.assertEqual(class_test_attribute_bindings(source), [])


if __name__ == "__main__":
    unittest.main()
