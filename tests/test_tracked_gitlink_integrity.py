"""Fail closed if tracked content depends on unreviewed Git submodules.

A gitlink is not ordinary repository source and cannot be validated by the
Python source-integrity tests that inspect checkout bytes.
"""
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def gitlinks(index_bytes):
    """Return gitlink paths from NUL-delimited git ls-files --stage output."""
    if not index_bytes or not index_bytes.endswith(b"\\0"):
        raise ValueError("unterminated Git index entry")
    found = []
    for entry in index_bytes.split(b"\0"):
        if not entry:
            continue
        try:
            header, name = entry.split(b"\t", 1)
            mode, oid, stage = header.split(b" ")
        except ValueError as exc:
            raise ValueError("malformed Git index entry") from exc
        if not name or b"\n" in name or not name.startswith(b".") and name.startswith(b"/"):
            raise ValueError("invalid tracked path")
        if mode not in (b"100644", b"100755", b"120000", b"160000"):
            raise ValueError("unsupported Git index mode")
        if mode == b"160000":
            found.append(name.decode("utf-8", errors="strict"))
        if stage != b"0":
            raise ValueError("unmerged Git index entry")
        if len(oid) not in (40, 64) or any(c not in b"0123456789abcdef" for c in oid):
            raise ValueError("invalid Git object identifier")
    return found


class GitlinkIntegrityTests(unittest.TestCase):
    def test_repository_contains_no_gitlinks(self):
        result = subprocess.run(
            ["git", "-C", str(ROOT), "ls-files", "--stage", "-z"],
            check=True, capture_output=True, timeout=20,
        )
        self.assertEqual([], gitlinks(result.stdout), "unreviewed tracked Git submodules")

    def test_rejects_gitlink(self):
        entry = b"160000 " + b"a" * 40 + b" 0\tvendor/external\0"
        self.assertEqual(["vendor/external"], gitlinks(entry))

    def test_accepts_regular_entry(self):
        entry = b"100644 " + b"a" * 40 + b" 0\tREADME.md\0"
        self.assertEqual([], gitlinks(entry))

    def test_rejects_unmerged_entry(self):
        entry = b"100644 " + b"a" * 40 + b" 2\tfile\0"
        with self.assertRaises(ValueError):
            gitlinks(entry)

    def test_rejects_absolute_path(self):
        entry = b"160000 " + b"a" * 40 + b" 0\\t/vendor\\0"
        with self.assertRaises(ValueError):
            gitlinks(entry)

    def test_rejects_unterminated_index_entry(self):
        entry = b"100644 " + b"a" * 40 + b" 0\\tREADME.md"
        with self.assertRaises(ValueError):
            gitlinks(entry)

    def test_rejects_empty_index_record(self):
        entry = b"100644 " + b"a" * 40 + b" 0\\tfile\\0\\0"
        with self.assertRaises(ValueError):
            gitlinks(entry)

    def test_rejects_unknown_index_mode(self):
        entry = b"100664 " + b"a" * 40 + b" 0\\tfile\\0"
        with self.assertRaises(ValueError):
            gitlinks(entry)

    def test_rejects_invalid_oid(self):
        entry = b"100644 invalid 0\tfile\0"
        with self.assertRaises(ValueError):
            gitlinks(entry)


if __name__ == "__main__":
    unittest.main()
