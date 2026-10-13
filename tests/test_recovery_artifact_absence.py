"""Reject accidentally committed merge/rebase recovery artifacts.

Run: python3 -m unittest discover -s tests -p 'test_recovery_artifact_absence.py'
"""
import subprocess
import unittest
from pathlib import PurePosixPath


RECOVERY_SUFFIXES = (".orig", ".rej")


def recovery_artifacts(paths):
    """Return sorted tracked paths with merge/rebase recovery suffixes."""
    return sorted(path for path in paths if
                  PurePosixPath(path).name.endswith(RECOVERY_SUFFIXES))


def tracked_paths():
    result = subprocess.run(
        ["git", "ls-files", "-z", "--cached"],
        check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        timeout=20,
    )
    return [part.decode("utf-8", errors="strict")
            for part in result.stdout.split(b"\0") if part]


class RecoveryArtifactAbsenceTests(unittest.TestCase):
    def test_rejects_merge_and_rebase_recovery_files(self):
        self.assertEqual(
            recovery_artifacts([
                "src/Settings.kt.orig", "docs/acceptance.md.rej",
                "tests/test_example.py", "docs/legitimate.patch",
            ]),
            ["docs/acceptance.md.rej", "src/Settings.kt.orig"],
        )

    def test_ignores_suffixes_in_parent_directory_names(self):
        self.assertEqual(
            recovery_artifacts(["archive.orig/README.md", "reject.rej/file.txt"]),
            [],
        )

    def test_no_recovery_artifacts_are_tracked(self):
        offenders = recovery_artifacts(tracked_paths())
        self.assertEqual(offenders, [],
                         "Tracked merge/rebase recovery artifacts: " + repr(offenders))


if __name__ == "__main__":
    unittest.main()
