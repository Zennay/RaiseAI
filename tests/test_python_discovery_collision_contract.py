"""Guard against silent unittest discovery collisions in nested test packages.

Duplicate test_*.py module basenames may shadow one another when discovery adds
a package directory to sys.path, so passing CI may omit an entire contract file.
This is an independent, source-only quality check; no device access is needed.
"""
from collections import defaultdict
from pathlib import Path
import tempfile
import unittest


def collisions(root: Path) -> dict[str, tuple[str, ...]]:
    """Return duplicate discoverable test basenames and their relative paths."""
    groups = defaultdict(list)
    for file in root.rglob("test_*.py"):
        if file.is_file() and not file.is_symlink():
            groups[file.name].append(file.relative_to(root).as_posix())
    return {
        name: tuple(sorted(paths))
        for name, paths in sorted(groups.items())
        if len(paths) > 1
    }


class PythonDiscoveryCollisionContract(unittest.TestCase):
    def test_repository_has_unique_test_module_basenames(self):
        root = Path(__file__).resolve().parent
        self.assertEqual(
            collisions(root), {},
            "Duplicate Python test filenames can shadow unittest discovery",
        )

    def test_duplicate_nested_basename_is_detected(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for name in ("first/test_duplicate.py", "second/test_duplicate.py"):
                file = root / name
                file.parent.mkdir(parents=True, exist_ok=True)
                file.write_text("pass\n", encoding="utf-8")
            self.assertEqual(
                collisions(root),
                {"test_duplicate.py": (
                    "first/test_duplicate.py",
                    "second/test_duplicate.py",
                )},
            )

    def test_same_directory_names_with_distinct_module_basenames_pass(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for name in ("first/test_alpha.py", "second/test_beta.py"):
                file = root / name
                file.parent.mkdir(parents=True, exist_ok=True)
                file.write_text("pass\n", encoding="utf-8")
            self.assertEqual(collisions(root), {})

    def test_multiple_collision_groups_are_sorted_deterministically(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for name in (
                "z/test_zeta.py", "b/test_alpha.py", "a/test_zeta.py",
                "c/test_alpha.py", "d/test_unique.py",
            ):
                file = root / name
                file.parent.mkdir(parents=True, exist_ok=True)
                file.write_text("pass\n", encoding="utf-8")
            self.assertEqual(
                collisions(root),
                {
                    "test_alpha.py": ("b/test_alpha.py", "c/test_alpha.py"),
                    "test_zeta.py": ("a/test_zeta.py", "z/test_zeta.py"),
                },
            )

    def test_non_test_modules_do_not_trigger_collision(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for name in ("first/helper.py", "second/helper.py"):
                file = root / name
                file.parent.mkdir(parents=True, exist_ok=True)
                file.write_text("pass\n", encoding="utf-8")
            self.assertEqual(collisions(root), {})


if __name__ == "__main__":
    unittest.main()
