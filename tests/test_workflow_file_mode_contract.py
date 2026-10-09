"""Keep GitHub Actions workflow sources regular and non-executable in Git.

Workflow discovery is from the index rather than the local filesystem, so an
unexpected tracked entry cannot silently disappear from quality validation.
"""
import pathlib
import subprocess
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
PREFIX = ".github/workflows/"


def validate_workflow_index(raw: bytes) -> int:
    count = 0
    for record in raw.split(b"\0"):
        if not record:
            continue
        try:
            metadata, raw_path = record.split(b"\t", 1)
            mode, object_id, stage = metadata.decode("ascii").split()
            path = raw_path.decode("utf-8", "strict")
        except (UnicodeError, ValueError) as exc:
            raise ValueError("malformed Git index entry") from exc
        if not path.startswith(PREFIX):
            continue
        count += 1
        if not path.endswith((".yml", ".yaml")):
            raise ValueError(f"{path}: unexpected tracked workflow directory entry")
        if mode != "100644" or stage != "0":
            raise ValueError(f"{path}: workflow must be a stage-zero non-executable regular file")
        if len(object_id) not in (40, 64) or any(c not in "0123456789abcdef" for c in object_id):
            raise ValueError(f"{path}: invalid Git object identity")
    if not count:
        raise ValueError("no tracked GitHub Actions workflows discovered")
    return count


class WorkflowFileModeContractTests(unittest.TestCase):
    def test_tracked_workflow_index(self):
        raw = subprocess.check_output(
            ["git", "ls-files", "--stage", "-z"], cwd=ROOT
        )
        self.assertGreater(validate_workflow_index(raw), 0)

    def test_valid_index_fixture(self):
        fixture = (
            b"100644 " + b"a" * 40 + b" 0\t.github/workflows/check.yml\0"
            + b"100755 " + b"b" * 40 + b" 0\ttools/helper.sh\0"
        )
        self.assertEqual(validate_workflow_index(fixture), 1)

    def test_rejects_executable_symlink_and_unmerged_workflows(self):
        for mode, stage in (("100755", "0"), ("120000", "0"), ("100644", "2")):
            with self.subTest(mode=mode, stage=stage):
                fixture = f"{mode} {'a' * 40} {stage}\t.github/workflows/check.yml\0".encode()
                with self.assertRaisesRegex(ValueError, "stage-zero non-executable"):
                    validate_workflow_index(fixture)

    def test_rejects_unexpected_workflow_files(self):
        fixture = b"100644 " + b"a" * 40 + b" 0\t.github/workflows/check.txt\0"
        with self.assertRaisesRegex(ValueError, "unexpected tracked"):
            validate_workflow_index(fixture)

    def test_rejects_empty_workflow_discovery(self):
        with self.assertRaisesRegex(ValueError, "no tracked"):
            validate_workflow_index(b"100644 " + b"a" * 40 + b" 0\tREADME.md\0")
