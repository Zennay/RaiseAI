"""Reject tracked editor backup copies without excluding normal source files.

Run: python3 -m unittest discover -s tests -p 'test_editor_backup_absence.py'
"""
import subprocess
import unittest
from pathlib import PurePosixPath


def backup_artifacts(paths):
    """Find Emacs/Vim backup filenames, including numbered Emacs versions."""
    result = []
    for path in paths:
        name = PurePosixPath(path).name
        numbered = ("~" in name and name.rsplit("~", 2)[-1] == ""
                    and ".~" in name
                    and name.rsplit(".~", 1)[-1][:-1].isdigit())
        if name.endswith("~") or numbered:
            result.append(path)
    return sorted(result)


def index_paths():
    result = subprocess.run(["git", "ls-files", "--cached", "-z"],
                            check=True, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, timeout=20)
    return [value.decode("utf-8", "strict") for value
            in result.stdout.split(b"\0") if value]


class EditorBackupAbsenceTests(unittest.TestCase):
    def test_rejects_simple_and_numbered_backups(self):
        files = ["README.md~", "src/Watch.kt.~1~", "src/Watch.kt.~234~"]
        self.assertEqual(backup_artifacts(files), sorted(files))

    def test_accepts_regular_files_and_backup_named_directories(self):
        self.assertEqual(backup_artifacts([
            "docs/guide.md", "backup~/docs.txt",
            "src/Watch.kt.~1", "src/Watch.kt.bak",
        ]), [])

    def test_git_index_contains_no_editor_backups(self):
        self.assertEqual(backup_artifacts(index_paths()), [],
                         "Tracked editor backup artifacts detected")


if __name__ == "__main__":
    unittest.main()
