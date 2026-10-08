"""Fail closed on invisible or terminal-control characters in tracked paths.

Git accepts paths that are difficult to distinguish in CI logs and review UIs.
This independent contract validates names without touching runtime or release data.
"""
import pathlib
import subprocess
import tempfile
import unittest
import unicodedata


ROOT = pathlib.Path(__file__).resolve().parents[1]
BIDI_FORMATS = {
    "\u061c", "\u200e", "\u200f", "\u202a", "\u202b", "\u202c",
    "\u202d", "\u202e", "\u2066", "\u2067", "\u2068", "\u2069",
}


def validate_tracked_path(raw: bytes) -> str:
    if not raw or b"\x00" in raw:
        raise ValueError("tracked path must be nonempty and NUL-free")
    try:
        name = raw.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise ValueError("tracked path must be valid UTF-8") from exc
    if name.startswith("/") or "\\" in name:
        raise ValueError("tracked path must be repository-relative POSIX")
    if any(component in ("", ".", "..") for component in name.split("/")):
        raise ValueError("tracked path has an ambiguous component")
    for char in name:
        if unicodedata.category(char) in {"Cc", "Cf", "Cs"} or char in BIDI_FORMATS:
            raise ValueError("tracked path contains invisible/control Unicode")
    return name


def tracked_paths(root: pathlib.Path = ROOT):
    raw = subprocess.check_output(["git", "ls-files", "-z"], cwd=root)
    if not raw.endswith(b"\x00"):
        raise ValueError("git ls-files output must be NUL-terminated")
    paths = [validate_tracked_path(part) for part in raw[:-1].split(b"\x00")]
    if not paths or len(paths) != len(set(paths)):
        raise ValueError("tracked paths must be nonempty and unique")
    return paths


class TrackedPathControlContractTests(unittest.TestCase):
    def test_repository_tracked_paths_are_unambiguous(self):
        self.assertTrue(tracked_paths())

    def test_safe_unicode_and_nested_paths(self):
        for name in ("README.md", "docs/release-notes.md", "docs/caf\u00e9.md"):
            with self.subTest(name=name):
                self.assertEqual(validate_tracked_path(name.encode()), name)

    def test_rejects_invisible_control_and_invalid_paths(self):
        bad = (
            b"", b"x\x00y", b"bad\xff", b"/absolute", b"a//b",
            b"a/./b", b"a/../b", b"a\\b", b"tab\tname",
            b"new\nline", "spoof\u202eexe.txt".encode(),
            "zero\u200bwidth.txt".encode(), "mark\u200f.txt".encode(),
        )
        for name in bad:
            with self.subTest(name=name):
                with self.assertRaises(ValueError):
                    validate_tracked_path(name)

    def test_git_discovery_preserves_spaces_without_shell_split(self):
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            subprocess.run(["git", "init", "-q", str(root)], check=True)
            (root / "file with spaces.txt").write_text("ok\n", encoding="utf-8")
            subprocess.run(["git", "add", "--", "file with spaces.txt"], cwd=root, check=True)
            self.assertEqual(tracked_paths(root), ["file with spaces.txt"])


if __name__ == "__main__":
    unittest.main()
