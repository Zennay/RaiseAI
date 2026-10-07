from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS_DIR = ROOT / ".github" / "workflows"
PULL_REQUEST_RE = re.compile(r"(?m)^  pull_request:\\s*(?:\\{\\})?\\s*(?:#.*)?$")
PULL_REQUEST_TARGET_RE = re.compile(
    r"(?m)^  pull_request_target:\\s*(?:\\{\\})?\\s*(?:#.*)?$"
)
SECRET_REF_RE = re.compile(r"\\$\\{\\{\\s*secrets\\.")


def workflow_paths() -> list[Path]:
    return sorted(
        {
            *WORKFLOWS_DIR.glob("*.yml"),
            *WORKFLOWS_DIR.glob("*.yaml"),
        }
    )


def write_permissions(text: str) -> list[str]:
    writes: list[str] = []
    lines = text.splitlines()
    for index, line in enumerate(lines):
        match = re.fullmatch(r"( *)permissions:\\s*", line)
        if not match:
            continue

        parent_indent = len(match.group(1))
        for child in lines[index + 1 :]:
            if not child.strip():
                continue

            child_indent = len(child) - len(child.lstrip(" "))
            if child_indent <= parent_indent:
                break

            permission = re.fullmatch(
                rf" {{{parent_indent + 2}}}([A-Za-z0-9_-]+):\\s*write\\s*(?:#.*)?",
                child,
            )
            if permission:
                writes.append(permission.group(1))

    return writes


class WorkflowPrivilegeBoundaryTests(unittest.TestCase):
    def test_pull_request_target_is_forbidden_repository_wide(self):
        paths = workflow_paths()
        self.assertTrue(paths, "workflow privilege guard must inspect at least one workflow")

        for path in paths:
            relative = path.relative_to(ROOT).as_posix()
            text = path.read_text(encoding="utf-8")
            with self.subTest(workflow=relative):
                self.assertIsNone(
                    PULL_REQUEST_TARGET_RE.search(text),
                    f"{relative}: pull_request_target is forbidden because it executes "
                    "untrusted PR context with base-repository privileges",
                )

    def test_pull_request_workflows_cannot_receive_secrets_or_write_permissions(self):
        paths = workflow_paths()
        self.assertTrue(paths, "workflow privilege guard must inspect at least one workflow")

        for path in paths:
            relative = path.relative_to(ROOT).as_posix()
            text = path.read_text(encoding="utf-8")
            if not PULL_REQUEST_RE.search(text):
                continue

            with self.subTest(workflow=relative):
                self.assertIsNone(
                    SECRET_REF_RE.search(text),
                    f"{relative}: pull_request workflows must not consume repository secrets",
                )
                self.assertEqual(
                    write_permissions(text),
                    [],
                    f"{relative}: pull_request workflows must not receive write token permissions",
                )

    def test_write_permission_parser_covers_top_level_and_job_scopes(self):
        fixture = """permissions:
  contents: write

jobs:
  verify:
    permissions:
      checks: write
      contents: read
"""
        self.assertEqual(write_permissions(fixture), ["contents", "checks"])

    def test_read_only_pull_request_fixture_is_allowed(self):
        fixture = """on:
  pull_request:

permissions:
  contents: read
"""
        self.assertIsNotNone(PULL_REQUEST_RE.search(fixture))
        self.assertIsNone(SECRET_REF_RE.search(fixture))
        self.assertEqual(write_permissions(fixture), [])

    def test_privileged_manual_fixture_stays_outside_pr_boundary(self):
        fixture = """on:
  workflow_dispatch:

permissions:
  contents: write

jobs:
  operate:
    runs-on: ubuntu-24.04
    steps:
      - run: echo "${{ secrets.OPERATOR_TOKEN }}"
"""
        self.assertIsNone(PULL_REQUEST_RE.search(fixture))
        self.assertEqual(write_permissions(fixture), ["contents"])
        self.assertIsNotNone(SECRET_REF_RE.search(fixture))


if __name__ == "__main__":
    unittest.main()
