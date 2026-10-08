"""Fail-closed byte-integrity gate for Git-tracked JSON source files.

This is deliberately separate from physical-session evidence: it only examines
repository-tracked source JSON and never touches on-device evidence.
"""
import os
from pathlib import Path
import stat
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
MAX_BYTES = 2 * 1024 * 1024


def validate_json_source(path: Path, *, max_bytes: int = MAX_BYTES) -> None:
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    fd = os.open(path, flags)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode):
            raise ValueError("JSON source must be a regular, non-symlink file")
        if info.st_size > max_bytes:
            raise ValueError("JSON source exceeds size bound")
        with os.fdopen(fd, "rb", closefd=False) as source:
            raw = source.read(max_bytes + 1)
        if len(raw) > max_bytes:
            raise ValueError("JSON source exceeds size bound")
        if raw.startswith(b"\\xef\\xbb\\xbf") or b"\\x00" in raw:
            raise ValueError("JSON source contains forbidden bytes")
        raw.decode("utf-8", errors="strict")
    finally:
        os.close(fd)


def tracked_json_paths(root: Path):
    result = subprocess.run(
        ["git", "-C", str(root), "ls-files", "--stage", "-z", "--", "*.json"],
        check=True, capture_output=True,
    )
    for entry in result.stdout.split(b"\x00"):
        if not entry:
            continue
        header, sep, filename = entry.partition(b"\t")
        if not sep:
            raise ValueError("Malformed Git index entry")
        fields = header.split()
        if len(fields) != 3 or fields[0] != b"100644" or fields[2] != b"0":
            raise ValueError("Tracked JSON must be an ordinary stage-zero source")
        relative = os.fsdecode(filename)
        path = Path(relative)
        if path.is_absolute() or ".." in path.parts:
            raise ValueError("Unexpected tracked JSON path")
        yield root / path


class TrackedJsonSourceIntegrityTests(unittest.TestCase):
    def test_current_tracked_json_sources(self):
        for path in tracked_json_paths(ROOT):
            with self.subTest(path=str(path)):
                validate_json_source(path)

    def test_valid_utf8(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "valid.json"
            path.write_bytes('{"label":"caf\\u00e9"}\n'.encode())
            validate_json_source(path)

    def test_forbidden_bytes_and_invalid_utf8(self):
        for payload in (b"\xef\xbb\xbf{}", b'{"x":"\x00"}', b"\xff{}"):
            with self.subTest(payload=payload), tempfile.TemporaryDirectory() as folder:
                path = Path(folder) / "bad.json"
                path.write_bytes(payload)
                with self.assertRaises((ValueError, UnicodeDecodeError)):
                    validate_json_source(path)

    def test_rejects_oversized_and_symlink(self):
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / "target.json"
            target.write_bytes(b"{}")
            link = Path(folder) / "link.json"
            link.symlink_to(target)
            with self.assertRaises((OSError, ValueError)):
                validate_json_source(link)
            with self.assertRaises(ValueError):
                validate_json_source(target, max_bytes=1)


if __name__ == "__main__":
    unittest.main()
