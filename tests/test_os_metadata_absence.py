"""Disallow host OS metadata files in the tracked Raise AI source tree.

Run: python3 -m unittest discover -s tests -p 'test_os_metadata_absence.py'
"""
import subprocess
import unittest
from pathlib import PurePosixPath


HOST_METADATA_NAMES = frozenset({".DS_Store", "Thumbs.db", "ehthumbs.db",
                                 "Desktop.ini", ".Spotlight-V100",
                                 ".Trashes"})


def host_metadata_paths(paths):
    """Return tracked OS metadata paths without matching innocent substrings."""
    return sorted(path for path in paths if
                  any(part in HOST_METADATA_NAMES
                      or part.startswith("._") for part in
                      PurePosixPath(path).parts))


def tracked_paths():
    completed = subprocess.run(
        ["git", "ls-files", "--cached", "-z"],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=20,
    )
    return [part.decode("utf-8", "strict") for part in
            completed.stdout.split(b"\x00") if part]


class HostMetadataAbsenceTests(unittest.TestCase):
    def test_rejects_mac_and_windows_metadata(self):
        candidates = ["assets/.DS_Store", "docs/Thumbs.db",
                      "images/._logo.png", "build/Desktop.ini"]
        self.assertEqual(host_metadata_paths(candidates), sorted(candidates))

    def test_preserves_similarly_named_legitimate_files(self):
        self.assertEqual(host_metadata_paths([
            "docs/Thumbs.db.md", "assets/DS_Store.txt",
            "docs/readme.md", "images/logo.png",
        ]), [])

    def test_metadata_directories_are_also_forbidden(self):
        self.assertEqual(host_metadata_paths([
            "assets/.Spotlight-V100/file", "cache/.Trashes/entry",
        ]), ["assets/.Spotlight-V100/file", "cache/.Trashes/entry"])

    def test_tracked_sources_have_no_host_metadata(self):
        self.assertEqual(host_metadata_paths(tracked_paths()), [],
                         "Host OS metadata files must not be committed")


if __name__ == "__main__":
    unittest.main()
