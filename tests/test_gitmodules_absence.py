"""Reject tracked Git submodule configuration, even without a gitlink.

A .gitmodules file can carry submodule URLs and commands into future tooling;
this repository intentionally contains no third-party Git submodules.
Run with: python3 -m unittest discover -s tests -p 'test_gitmodules_absence.py'
"""
import pathlib
import subprocess
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]


def forbidden_gitmodules_paths(paths: list[str]) -> list[str]:
    """Match Git's .gitmodules filename at any depth, case-insensitively."""
    return [path for path in paths if path.split("/")[-1].casefold() == ".gitmodules"]


def tracked_paths() -> list[str]:
    raw = subprocess.check_output(["git", "ls-files", "-z"], cwd=ROOT)
    return [entry for entry in raw.decode("utf-8", "strict").split("\0") if entry]


class GitmodulesAbsenceTests(unittest.TestCase):
    def test_repository_has_no_tracked_gitmodules_configuration(self):
        paths = tracked_paths()
        self.assertTrue(paths, "Git index discovery must not be empty")
        self.assertEqual(forbidden_gitmodules_paths(paths), [])

    def test_rejects_root_nested_and_case_variant_gitmodules(self):
        for path in (".gitmodules", "tools/.gitmodules", "third_party/.GITMODULES"):
            with self.subTest(path=path):
                self.assertEqual(forbidden_gitmodules_paths([path]), [path])

    def test_does_not_confuse_similarly_named_files(self):
        self.assertEqual(
            forbidden_gitmodules_paths(["docs/gitmodules.md", ".gitmodules.example", "tools/modules"]),
            [],
        )


if __name__ == "__main__":
    unittest.main()
