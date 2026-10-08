"""Reject Git-tracked path collisions on case-insensitive filesystems.

Run: python3 -m unittest discover -s tests -p 'test_tracked_path_casefold.py'
"""
import pathlib
import subprocess
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]


def validate_portable_paths(paths: list[str]) -> None:
    """Reject casefold-equivalent full paths and directory/file ambiguity."""
    seen: dict[str, str] = {}
    files: set[str] = set()
    directories: dict[str, str] = {}
    for path in paths:
        if not path or path.startswith("/") or "\0" in path:
            raise ValueError(f"invalid tracked path: {path!r}")
        parts = path.split("/")
        if any(part in ("", ".", "..") for part in parts):
            raise ValueError(f"noncanonical tracked path: {path!r}")
        folded = path.casefold()
        previous = seen.get(folded)
        if previous is not None:
            raise ValueError(f"case-insensitive path collision: {previous!r} and {path!r}")
        seen[folded] = path
        files.add(folded)
        for index in range(1, len(parts)):
            directory = "/".join(parts[:index])
            directories.setdefault(directory.casefold(), directory)
    for folded, path in files.intersection(directories):
        raise ValueError(f"file/directory path collision: {seen[folded]!r} and {directories[folded]!r}")


def tracked_paths() -> list[str]:
    raw = subprocess.check_output(["git", "ls-files", "-z"], cwd=ROOT)
    return [part.decode("utf-8", "strict") for part in raw.split(b"\0") if part]


class TrackedPathCasefoldTests(unittest.TestCase):
    def test_git_index_has_no_casefold_collisions(self):
        paths = tracked_paths()
        self.assertTrue(paths, "expected tracked files")
        validate_portable_paths(paths)

    def test_accepts_distinct_paths(self):
        validate_portable_paths(["README.md", "src/Main.kt", "tests/test_main.py"])

    def test_rejects_filename_collision(self):
        with self.assertRaisesRegex(ValueError, "case-insensitive path collision"):
            validate_portable_paths(["src/Watch.kt", "src/watch.kt"])

    def test_rejects_directory_case_collision(self):
        with self.assertRaisesRegex(ValueError, "case-insensitive path collision"):
            validate_portable_paths(["Src/main.kt", "src/main.kt"])

    def test_rejects_unicode_casefold_collision(self):
        with self.assertRaisesRegex(ValueError, "case-insensitive path collision"):
            validate_portable_paths(["Straße.txt", "STRASSE.txt"])

    def test_rejects_file_directory_collision(self):
        with self.assertRaisesRegex(ValueError, "file/directory path collision"):
            validate_portable_paths(["Assets", "assets/icon.png"])

    def test_rejects_noncanonical_components(self):
        for path in ("a//b", "a/./b", "a/../b", "/absolute"):
            with self.subTest(path=path), self.assertRaises(ValueError):
                validate_portable_paths([path])


if __name__ == "__main__":
    unittest.main()
