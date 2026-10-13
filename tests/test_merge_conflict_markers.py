"""Reject unresolved Git conflict markers in production text surfaces.

Run: python3 -m unittest discover -s tests -p 'test_merge_conflict_markers.py'
"""
import pathlib
import re
import subprocess
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SOURCE_SUFFIXES = {".kt", ".java", ".gradle", ".py", ".js", ".mjs", ".yml", ".yaml", ".sh", ".ps1", ".command"}
CONFLICT_LINE = re.compile(r"^(?:<{7}(?: .*)?|={7}|>{7}(?: .*)?|\|{7}(?: .*)?)$", re.MULTILINE)


def validate_no_conflict_markers(source: str, path: str) -> None:
    """Reject full-line Git merge/diff3 markers, never arbitrary inline text."""
    match = CONFLICT_LINE.search(source)
    if match is not None:
        line_number = source.count("\n", 0, match.start()) + 1
        raise ValueError(f"{path}:{line_number}: unresolved Git conflict marker")


def production_text_paths() -> list[str]:
    raw = subprocess.check_output(["git", "ls-files", "-z"], cwd=ROOT)
    names = [name.decode("utf-8", "strict") for name in raw.split(b"\0") if name]
    return [
        name for name in names
        if not name.startswith(("fixtures/", "docs/"))
        and pathlib.PurePosixPath(name).suffix.lower() in SOURCE_SUFFIXES
    ]


class MergeConflictMarkerTests(unittest.TestCase):
    def test_all_tracked_production_sources_are_conflict_free(self):
        paths = production_text_paths()
        self.assertTrue(paths, "expected tracked production sources")
        for name in paths:
            with self.subTest(path=name):
                source = (ROOT / name).read_text(encoding="utf-8")
                validate_no_conflict_markers(source, name)

    def test_tracked_test_sources_are_not_exempt(self):
        paths = production_text_paths()
        self.assertIn("tests/test_merge_conflict_markers.py", paths)

    def test_rejects_merge_and_diff3_markers(self):
        for marker in ("<<<<<<< HEAD", "=======", ">>>>>>> feature", "||||||| base"):
            with self.subTest(marker=marker):
                with self.assertRaisesRegex(ValueError, "unresolved Git conflict marker"):
                    validate_no_conflict_markers("ok\n" + marker + "\n", "app.kt")

    def test_accepts_legitimate_inline_and_short_delimiters(self):
        for source in ("let x = \"<<<<<<< HEAD\"\n", "======\n", "some ======= text\n", "const x = 1;\n"):
            with self.subTest(source=source):
                validate_no_conflict_markers(source, "app.kt")


if __name__ == "__main__":
    unittest.main()
