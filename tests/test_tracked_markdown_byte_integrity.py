"""Fail closed on malformed Git-tracked Markdown documentation bytes.

This is intentionally independent of the frozen physical Watch acceptance artifact.
"""
import pathlib
import subprocess
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
MAX_MARKDOWN_BYTES = 2 * 1024 * 1024


def validate_markdown_bytes(data: bytes, name: str) -> None:
    if len(data) > MAX_MARKDOWN_BYTES:
        raise ValueError(f"{name}: Markdown exceeds the 2 MiB source budget")
    if data.startswith(b"\xef\xbb\xbf"):
        raise ValueError(f"{name}: UTF-8 BOM is forbidden")
    if b"\x00" in data:
        raise ValueError(f"{name}: NUL byte is forbidden")
    try:
        data.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise ValueError(f"{name}: Markdown must be strict UTF-8") from exc


def tracked_markdown_paths() -> list[str]:
    output = subprocess.check_output(
        ["git", "ls-files", "--stage", "-z", "--", "*.md", "*.MD"],
        cwd=ROOT,
    )
    paths = []
    for record in output.split(b"\x00"):
        if not record:
            continue
        metadata, raw_path = record.split(b"\t", 1)
        mode, object_id, stage = metadata.decode("ascii").split()
        path = raw_path.decode("utf-8", errors="strict")
        if mode not in ("100644", "100755") or stage != "0":
            raise ValueError(f"{path}: Markdown index entry must be stage-zero regular file")
        if len(object_id) not in (40, 64) or any(c not in "0123456789abcdef" for c in object_id):
            raise ValueError(f"{path}: invalid Git object identifier")
        paths.append(path)
    return paths


class TrackedMarkdownByteIntegrityTests(unittest.TestCase):
    def test_tracked_markdown_is_strict_utf8(self):
        paths = tracked_markdown_paths()
        self.assertTrue(paths, "expected tracked Markdown documents")
        for path in paths:
            with self.subTest(path=path):
                candidate = ROOT / path
                self.assertFalse(candidate.is_symlink(), path)
                self.assertTrue(candidate.is_file(), path)
                with candidate.open("rb") as source:
                    data = source.read(MAX_MARKDOWN_BYTES + 1)
                validate_markdown_bytes(data, path)

    def test_valid_utf8_and_budget_boundary(self):
        validate_markdown_bytes("Raise AI — test".encode(), "valid.md")
        validate_markdown_bytes(b"a" * MAX_MARKDOWN_BYTES, "limit.md")

    def test_reject_bom_nul_invalid_utf8_and_oversize(self):
        for data in (
            b"\xef\xbb\xbf# Title",
            b"prefix\x00suffix",
            b"\xff",
            b"a" * (MAX_MARKDOWN_BYTES + 1),
        ):
            with self.subTest(data_prefix=data[:12]):
                with self.assertRaises(ValueError):
                    validate_markdown_bytes(data, "bad.md")


if __name__ == "__main__":
    unittest.main()
