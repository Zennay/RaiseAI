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


class PythonSourceByteIntegrityTests(unittest.TestCase):
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
                self.assertFalse(data.startswith(b"\xef\xbb\xbf"), "Python source contains a UTF-8 BOM")
                self.assertNotIn(b"\0", data, "Python source contains NUL bytes")
                data.decode("utf-8", errors="strict")


if __name__ == "__main__":
    unittest.main()
