"""Keep local editor swap/backup artifacts out of tracked release sources.

Run: python3 -m unittest discover -s tests -p 'test_editor_artifact_absence.py'
"""
import subprocess
import unittest
from pathlib import PurePosixPath


EDITOR_SUFFIXES = (".swp", ".swo", ".swx", ".swn")


def editor_artifacts(paths):
    offenders = []
    for path in paths:
        name = PurePosixPath(path).name
        if name.endswith(EDITOR_SUFFIXES) or (
            name.startswith(".#") and len(name) > 2
        ):
            offenders.append(path)
    return sorted(offenders)


def git_index_paths():
    result = subprocess.run(
        ["git", "ls-files", "--cached", "-z"],
        check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        timeout=20,
    )
    return [entry.decode("utf-8", "strict") for entry in
            result.stdout.split(b"\x00") if entry]


class EditorArtifactAbsenceTests(unittest.TestCase):
    def test_detects_vim_swap_and_emacs_lock_files(self):
        paths = ["src/.Main.kt.swp", "docs/notes.swo", "docs/.#draft.md",
                 "src/.Main.kt.swx", "README.md"]
        self.assertEqual(editor_artifacts(paths), sorted(paths[:-1]))

    def test_does_not_reject_parent_name_or_other_dotfiles(self):
        self.assertEqual(editor_artifacts([
            "src.swp/Main.kt", "docs/.editorconfig", "docs/.#",
            "notes.swap", "docs/.#dir/normal.txt",
        ]), [])

    def test_repository_index_contains_no_editor_artifacts(self):
        self.assertEqual(
            editor_artifacts(git_index_paths()), [],
            "Tracked editor swap/lock artifacts must not ship",
        )


if __name__ == "__main__":
    unittest.main()
