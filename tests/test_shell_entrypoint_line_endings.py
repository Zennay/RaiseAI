"""Ensure tracked shell entrypoints retain portable, unambiguous bytes.

Runs under unittest discovery; no shell interpreter or watch hardware required.
"""
import os
from pathlib import Path
import stat
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]
MAX_SHELL_BYTES = 2 * 1024 * 1024


def invalid_shell_bytes(data: bytes) -> str | None:
    if data.startswith(b"\xef\xbb\xbf"):
        return "UTF-8 BOM"
    if b"\x00" in data:
        return "NUL byte"
    if b"\r" in data:
        return "carriage return"
    return None


def read_regular_shell(path: Path) -> bytes:
    """Open once, reject symlinks/FIFOs, and bound the read."""
    flags = os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW
    fd = os.open(path, flags)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode):
            raise ValueError("not a regular file")
        if info.st_size > MAX_SHELL_BYTES:
            raise ValueError("shell entrypoint exceeds size limit")
        with os.fdopen(os.dup(fd), "rb") as stream:
            data = stream.read(MAX_SHELL_BYTES + 1)
        if len(data) > MAX_SHELL_BYTES:
            raise ValueError("shell entrypoint exceeds size limit")
        return data
    finally:
        os.close(fd)


class ShellEntrypointByteIntegrity(unittest.TestCase):
    def test_fixtures(self):
        self.assertIsNone(invalid_shell_bytes(b"#!/bin/sh\necho ok\n"))
        for value in (b"\xef\xbb\xbf#!/bin/sh\n", b"echo a\x00b\n",
                      b"#!/bin/bash\r\necho ok\r\n", b"echo x\r"):
            with self.subTest(value=value):
                self.assertIsNotNone(invalid_shell_bytes(value))

    def test_tracked_shell_entries(self):
        proc = subprocess.run(
            ["git", "ls-files", "-z", "--", "*.sh", "*.command"],
            cwd=ROOT, capture_output=True, check=True,
        )
        files = [x for x in proc.stdout.split(b"\x00") if x]
        self.assertTrue(files, "No tracked shell entrypoints were found")
        for raw_name in files:
            name = raw_name.decode("utf-8", "surrogateescape")
            with self.subTest(path=name):
                path = ROOT / name
                self.assertIsNone(
                    invalid_shell_bytes(read_regular_shell(path)),
                    f"{name}: prohibited shell byte sequence",
                )


if __name__ == "__main__":
    unittest.main()
