"""Fail-closed byte integrity checks for tracked GitHub Actions workflows.

This contract is intentionally independent from workflow mode, YAML semantics,
and action pinning tests. It does not execute workflows or need credentials.
"""
from __future__ import annotations

import pathlib
import subprocess
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[1]
MAX_WORKFLOW_BYTES = 512 * 1024


def validate_workflow_bytes(data: bytes) -> None:
    if not data:
        raise ValueError("empty workflow")
    if len(data) > MAX_WORKFLOW_BYTES:
        raise ValueError("oversized workflow")
    if data.startswith(b"\xef\xbb\xbf"):
        raise ValueError("UTF-8 BOM")
    if b"\x00" in data:
        raise ValueError("NUL byte")
    if b"\r" in data:
        raise ValueError("carriage return")
    try:
        data.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise ValueError("invalid UTF-8") from exc
    if not data.endswith(b"\n"):
        raise ValueError("missing final newline")


def tracked_workflow_paths(root: pathlib.Path) -> list[pathlib.Path]:
    output = subprocess.check_output(
        ["git", "-C", str(root), "ls-files", "-z", "--", ".github/workflows"],
    )
    result = []
    for raw in output.split(b"\x00"):
        if not raw:
            continue
        path = pathlib.Path(raw.decode("utf-8", errors="strict"))
        if path.suffix in {".yml", ".yaml"} and path.parent.as_posix() == ".github/workflows":
            result.append(path)
    return result


class WorkflowByteIntegrityTests(unittest.TestCase):
    def test_accepts_canonical_utf8_workflow(self) -> None:
        validate_workflow_bytes("name: Café\non: workflow_dispatch\n".encode("utf-8"))

    def test_rejects_empty_bom_nul_cr_invalid_utf8_and_no_final_newline(self) -> None:
        samples = [
            b"",
            b"\xef\xbb\xbfname: test\n",
            b"name: te\x00st\n",
            b"name: test\r\n",
            b"name: \xff\n",
            b"name: test",
        ]
        for sample in samples:
            with self.subTest(sample=sample):
                with self.assertRaises(ValueError):
                    validate_workflow_bytes(sample)

    def test_accepts_exact_size_boundary(self) -> None:
        validate_workflow_bytes(b"a" * (MAX_WORKFLOW_BYTES - 1) + b"\n")

    def test_rejects_oversized_workflow(self) -> None:
        with self.assertRaisesRegex(ValueError, "oversized"):
            validate_workflow_bytes(b"a" * (MAX_WORKFLOW_BYTES + 1))

    def test_workflow_discovery_only_includes_top_level_yaml(self) -> None:
        tracked = (
            b".github/workflows/build.yml\x00"
            b".github/workflows/check.yaml\x00"
            b".github/workflows/README.md\x00"
            b".github/workflows/nested/ignored.yml\x00"
            b"tests/not-a-workflow.yml\x00"
        )
        with mock.patch("subprocess.check_output", return_value=tracked) as check:
            paths = tracked_workflow_paths(ROOT)
        self.assertEqual(
            paths,
            [
                pathlib.Path(".github/workflows/build.yml"),
                pathlib.Path(".github/workflows/check.yaml"),
            ],
        )
        self.assertEqual(
            check.call_args.args[0],
            ["git", "-C", str(ROOT), "ls-files", "-z", "--", ".github/workflows"],
        )

    def test_all_git_tracked_workflow_bytes_are_canonical(self) -> None:
        paths = tracked_workflow_paths(ROOT)
        self.assertTrue(paths, "No tracked workflows found: cannot establish coverage")
        for path in paths:
            with self.subTest(path=str(path)):
                absolute = ROOT / path
                self.assertTrue(absolute.is_file() and not absolute.is_symlink())
                validate_workflow_bytes(absolute.read_bytes())


if __name__ == "__main__":
    unittest.main()
