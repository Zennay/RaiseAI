"""Fail closed when repeated test class definitions shadow earlier unittest cases."""
import ast
from pathlib import Path
import unittest


def repeated_classes(source: str) -> tuple[str, ...]:
    tree = ast.parse(source)
    findings = []

    def inspect(statements, parents=()):
        seen = set()
        for node in statements:
            if not isinstance(node, ast.ClassDef):
                continue
            qualified = ".".join((*parents, node.name))
            if node.name in seen:
                findings.append(qualified)
            seen.add(node.name)
            inspect(node.body, (*parents, node.name))

    inspect(tree.body)
    return tuple(sorted(findings))


class PythonTestClassShadowingContract(unittest.TestCase):
    def test_repository_test_files_have_no_repeated_classes(self):
        root = Path(__file__).resolve().parent
        duplicates = {}
        for path in sorted(root.rglob("test_*.py")):
            if path.is_symlink() or not path.is_file():
                continue
            matches = repeated_classes(path.read_text(encoding="utf-8"))
            if matches:
                duplicates[path.relative_to(root).as_posix()] = matches
        self.assertEqual(duplicates, {}, "Repeated class definitions can hide earlier tests")

    def test_two_top_level_classes_with_same_name_fail(self):
        source = "class TestSame: pass\nclass TestSame: pass\n"
        self.assertEqual(repeated_classes(source), ("TestSame",))

    def test_identically_named_nested_classes_under_different_parents_pass(self):
        source = (
            "class First:\n    class TestInner: pass\n"
            "class Second:\n    class TestInner: pass\n"
        )
        self.assertEqual(repeated_classes(source), ())

    def test_nested_duplicate_reports_qualified_name(self):
        source = (
            "class Outer:\n"
            "    class TestInner: pass\n"
            "    class TestInner: pass\n"
        )
        self.assertEqual(repeated_classes(source), ("Outer.TestInner",))

    def test_distinct_class_names_pass(self):
        self.assertEqual(repeated_classes("class TestOne: pass\nclass TestTwo: pass\n"), ())


if __name__ == "__main__":
    unittest.main()
