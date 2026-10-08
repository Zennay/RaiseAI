"""Prevent accidental commits of generated Python interpreter artifacts.

Git's index, not the working tree, defines the committed surface.
"""
import pathlib
import subprocess
import unittest
from unittest import mock


ROOT = pathlib.Path(__file__).resolve().parents[1]
GENERATED_SUFFIXES = (".pyc", ".pyo")
GENERATED_DIRS = {"__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache", ".tox", ".nox"}


def validate_tracked_python_artifact_paths(paths: list[str]) -> None:
    if not paths:
        raise ValueError("tracked file discovery must not be empty")
    for path in paths:
        parts = pathlib.PurePosixPath(path).parts
        if any(part in GENERATED_DIRS for part in parts):
            raise ValueError(f"{path!r}: generated Python cache directory is tracked")
        if path.lower().endswith(GENERATED_SUFFIXES):
            raise ValueError(f"{path!r}: generated Python bytecode is tracked")


def tracked_paths() -> list[str]:
    raw = subprocess.check_output(["git", "ls-files", "-z"], cwd=ROOT)
    if not raw or not raw.endswith(b"\0"):
        raise ValueError("tracked file discovery must be nonempty and NUL terminated")
    return [path.decode("utf-8", "strict") for path in raw[:-1].split(b"\0")]


class TrackedPythonArtifactHygieneTests(unittest.TestCase):
    def test_repository_tracks_no_generated_python_artifacts(self):
        validate_tracked_python_artifact_paths(tracked_paths())

    def test_rejects_interpreter_bytecode_and_cache_directories(self):
        for path in (
            "pkg/module.pyc", "pkg/module.PYO", "__pycache__/module.pyc",
            "tests/.pytest_cache/v/cache/nodeids", "pkg/.mypy_cache/data.json",
            ".ruff_cache/0", ".tox/py312/log", ".nox/lint/log",
        ):
            with self.subTest(path=path):
                with self.assertRaisesRegex(ValueError, "generated Python"):
                    validate_tracked_python_artifact_paths([path])

    def test_does_not_reject_normal_python_source_or_documentation(self):
        validate_tracked_python_artifact_paths([
            "tests/test_tracked_python_artifact_hygiene.py",
            "docs/python-cache-policy.md", "gateway/package.json",
        ])

    def test_git_index_discovery_rejects_truncated_and_invalid_utf8(self):
        for raw in (b"", b"file.py", b"\\xff\\0"):
            with self.subTest(raw=raw):
                with mock.patch("subprocess.check_output", return_value=raw):
                    with self.assertRaises((ValueError, UnicodeDecodeError)):
                        tracked_paths()

    def test_git_index_discovery_decodes_nul_delimited_paths(self):
        with mock.patch(
            "subprocess.check_output", return_value=b"src/main.py\\0tests/check.py\\0"
        ):
            self.assertEqual(tracked_paths(), ["src/main.py", "tests/check.py"])

    def test_empty_index_fails_closed(self):
        with self.assertRaisesRegex(ValueError, "must not be empty"):
            validate_tracked_python_artifact_paths([])


if __name__ == "__main__":
    unittest.main()
