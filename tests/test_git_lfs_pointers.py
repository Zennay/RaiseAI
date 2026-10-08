"""Ensure tracked files contain real content, not unresolved Git LFS pointers.

Run: python3 -m unittest discover -s tests -p 'test_git_lfs_pointers.py'
"""
import pathlib
import subprocess
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
LFS_HEADER = b"version https://git-lfs.github.com/spec/v1"


def is_lfs_pointer(data: bytes) -> bool:
    """Only flag Git LFS pointer headers at the start of a file."""
    return data.startswith(LFS_HEADER + b"\n") or data.startswith(LFS_HEADER + b"\r\n")


def tracked_paths() -> list[str]:
    raw = subprocess.check_output(["git", "ls-files", "-z"], cwd=ROOT)
    return [item for item in raw.decode("utf-8", "strict").split("\0") if item]


class GitLfsPointerTests(unittest.TestCase):
    def test_no_tracked_lfs_pointer_placeholders(self):
        paths = tracked_paths()
        self.assertTrue(paths, "repository tracked files must not be empty")
        offenders = []
        for relative in paths:
            path = ROOT / relative
            if path.is_symlink() or not path.is_file():
                continue  # Handled by the dedicated tracked-entry and symlink contracts.
            with path.open("rb") as stream:
                if is_lfs_pointer(stream.read(128)):
                    offenders.append(relative)
        self.assertEqual(offenders, [], f"unresolved Git LFS pointers: {offenders}")

    def test_detects_lf_and_crlf_lfs_pointer_headers(self):
        for newline in (b"\n", b"\r\n"):
            with self.subTest(newline=newline):
                self.assertTrue(is_lfs_pointer(LFS_HEADER + newline + b"oid sha256:abc\n"))

    def test_does_not_flag_documentation_or_header_prefix(self):
        self.assertFalse(is_lfs_pointer(b"Documentation: " + LFS_HEADER + b"\n"))
        self.assertFalse(is_lfs_pointer(LFS_HEADER + b"-other\n"))
        self.assertFalse(is_lfs_pointer(b"regular file\n"))


if __name__ == "__main__":
    unittest.main()
