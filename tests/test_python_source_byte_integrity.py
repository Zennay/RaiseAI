"""Regression guard for tracked Python source byte integrity.

Source files must remain inspectable as ordinary UTF-8 files; fixtures may
contain malformed bytes, but executable Python sources may not.
"""
import os
import stat
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAX_SOURCE_BYTES = 2 * 1024 * 1024


def tracked_python_sources():
    result = subprocess.run(
        ["git", "ls-files", "--stage", "-z"],
        cwd=ROOT,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    for record in result.stdout.split(b"\0"):
        if not record:
            continue
        metadata, separator, relative = record.partition(b"\t")
        if not separator:
            raise AssertionError("malformed Git index entry")
        fields = metadata.split()
        if len(fields) != 3 or fields[2] != b"0":
            raise AssertionError("noncanonical Git index stage")
        if not relative.endswith(b".py"):
            continue
        if fields[0] not in (b"100644", b"100755"):
            raise AssertionError(f"Python source has unexpected Git mode: {relative!r}")
        yield Path(os.fsdecode(relative))


def validate_source_bytes(data):
    if data.startswith(b"\xef\xbb\xbf"):
        raise ValueError("Python source contains UTF-8 BOM")
    if b"\0" in data:
        raise ValueError("Python source contains NUL bytes")
    data.decode("utf-8", errors="strict")


class PythonSourceByteIntegrityTests(unittest.TestCase):
    def test_rejects_bom_nul_and_malformed_utf8(self):
        for sample in (b"\xef\xbb\xbfprint(1)", b"print(1)\0", b"\xff"):
            with self.subTest(sample=sample), self.assertRaises((ValueError, UnicodeDecodeError)):
                validate_source_bytes(sample)

    def test_accepts_unicode_source(self):
        validate_source_bytes("message = 'café'\n".encode("utf-8"))

    def test_tracked_python_sources_are_regular_strict_utf8_without_bom_or_nul(self):
        paths = list(tracked_python_sources())
        self.assertTrue(paths, "No tracked Python sources found")
        for relative in paths:
            with self.subTest(source=str(relative)):
                path = ROOT / relative
                info = path.lstat()
                self.assertTrue(stat.S_ISREG(info.st_mode), "Python source is not a regular file")
                self.assertFalse(path.is_symlink(), "Python source is a symlink")
                self.assertLessEqual(info.st_size, MAX_SOURCE_BYTES, "Python source exceeds size budget")
                data = path.read_bytes()
                validate_source_bytes(data)


if __name__ == "__main__":
    unittest.main()
