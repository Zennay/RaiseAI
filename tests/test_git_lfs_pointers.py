"""Reject Git LFS pointer blobs in the tracked index, independently of checkout smudge.

Run: python3 -m unittest discover -s tests -p 'test_git_lfs_pointers.py'
"""
import pathlib
import subprocess
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
LFS_HEADER = b"version https://git-lfs.github.com/spec/v1"


def is_lfs_pointer(data: bytes) -> bool:
    return data.startswith(LFS_HEADER + b"\n") or data.startswith(LFS_HEADER + b"\r\n")


def index_blob_entries() -> list[tuple[str, str]]:
    """Retrieve trusted object ids from Git's NUL-delimited index, not checkout paths."""
    raw = subprocess.check_output(["git", "ls-files", "--stage", "-z"], cwd=ROOT)
    result = []
    for record in raw.split(b"\0"):
        if not record:
            continue
        metadata, name = record.split(b"\t", 1)
        mode, oid, stage = metadata.decode("ascii").split()
        if stage != "0" or mode not in {"100644", "100755"}:
            raise ValueError("noncanonical tracked Git index entry")
        result.append((name.decode("utf-8", "strict"), oid))
    return result


def blob_header(oid: str) -> bytes:
    blob = subprocess.check_output(["git", "cat-file", "blob", oid], cwd=ROOT)
    return blob[:128]


class GitLfsPointerTests(unittest.TestCase):
    def test_committed_blobs_are_not_lfs_placeholders(self):
        entries = index_blob_entries()
        self.assertTrue(entries, "repository tracked index must not be empty")
        offenders = [name for name, oid in entries if is_lfs_pointer(blob_header(oid))]
        self.assertEqual(offenders, [], f"committed Git LFS pointers: {offenders}")

    def test_detects_lf_and_crlf_pointer_headers(self):
        for newline in (b"\n", b"\r\n"):
            with self.subTest(newline=newline):
                self.assertTrue(is_lfs_pointer(LFS_HEADER + newline + b"oid sha256:abc\n"))

    def test_ignores_nonpointer_prefixes(self):
        self.assertFalse(is_lfs_pointer(b"Documentation: " + LFS_HEADER + b"\n"))
        self.assertFalse(is_lfs_pointer(LFS_HEADER + b"-other\n"))
        self.assertFalse(is_lfs_pointer(b"ordinary file\n"))


if __name__ == "__main__":
    unittest.main()
