from pathlib import Path
import re
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS_DIR = ROOT / ".github" / "workflows"
SECRET_REF_RE = re.compile(r"\$\{\{\s*secrets\.")
EXTERNAL_ACTION_RE = re.compile(
    r"(?m)^\s*(?:-\s*)?uses:\s*([^@\s]+)@([^\s#]+)"
)
IMMUTABLE_ACTION_REF_RE = re.compile(r"^[0-9a-f]{40}$")


def workflow_paths(root=ROOT) -> list[Path]:
    workflows = root / ".github" / "workflows"
    return sorted(
        {
            *workflows.glob("*.yml"),
            *workflows.glob("*.yaml"),
        }
    )


def workflow_events(path: Path) -> set[str]:
    script = r"""
require "psych"
raw = File.binread(ARGV.fetch(0))
raw.force_encoding(Encoding::UTF_8)
abort("invalid UTF-8") unless raw.valid_encoding?
tree = Psych.parse_stream(raw)
abort("YAML stream must contain exactly one document") unless tree.children.length == 1
root = tree.children.fetch(0).root
abort("workflow root must be a mapping") unless root.is_a?(Psych::Nodes::Mapping)

on_node = nil
root.children.each_slice(2) do |key_node, value_node|
  next unless key_node.is_a?(Psych::Nodes::Scalar) && key_node.value == "on"
  abort("workflow must declare on exactly once") if on_node
  on_node = value_node
end

events = []
case on_node
when Psych::Nodes::Scalar
  events << on_node.value
when Psych::Nodes::Sequence
  on_node.children.each do |event_node|
    abort("workflow event sequence entries must be scalars") unless event_node.is_a?(Psych::Nodes::Scalar)
    events << event_node.value
  end
when Psych::Nodes::Mapping
  on_node.children.each_slice(2) do |event_node, _config_node|
    abort("workflow event mapping keys must be scalars") unless event_node.is_a?(Psych::Nodes::Scalar)
    events << event_node.value
  end
when nil
  abort("workflow must declare an on trigger")
else
  abort("workflow on trigger must be a scalar, sequence, or mapping")
end

STDOUT.write(events.join("\0"))
STDOUT.write("\0") unless events.empty?
"""
    result = subprocess.run(
        ["ruby", "--disable-gems", "-e", script, str(path)],
        cwd=ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"{path}: workflow trigger semantic scan failed with exit "
            f"{result.returncode}: "
            f"{result.stderr.decode('utf-8', errors='replace').strip()}"
        )
    return {
        value.decode("utf-8", errors="strict")
        for value in result.stdout.split(b"\0")
        if value
    }


def write_permissions(text: str) -> list[str]:
    writes: list[str] = []
    lines = text.splitlines()
    for index, line in enumerate(lines):
        match = re.fullmatch(r"( *)permissions:\s*", line)
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
                rf" {{{parent_indent + 2}}}([A-Za-z0-9_-]+):\s*write\s*(?:#.*)?",
                child,
            )
            if permission:
                writes.append(permission.group(1))

    return writes


def external_action_refs(text: str) -> list[tuple[str, str]]:
    return EXTERNAL_ACTION_RE.findall(text)


class WorkflowPrivilegeBoundaryTests(unittest.TestCase):
    def test_pull_request_target_is_forbidden_repository_wide(self):
        paths = workflow_paths()
        self.assertTrue(paths, "workflow privilege guard must inspect at least one workflow")

        for path in paths:
            relative = path.relative_to(ROOT).as_posix()
            with self.subTest(workflow=relative):
                self.assertNotIn(
                    "pull_request_target",
                    workflow_events(path),
                    f"{relative}: pull_request_target is forbidden because it executes "
                    "untrusted PR context with base-repository privileges",
                )

    def test_pull_request_workflows_cannot_receive_secrets_or_write_permissions(self):
        paths = workflow_paths()
        self.assertTrue(paths, "workflow privilege guard must inspect at least one workflow")

        for path in paths:
            relative = path.relative_to(ROOT).as_posix()
            text = path.read_text(encoding="utf-8")
            if "pull_request" not in workflow_events(path):
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

    def test_pull_request_external_actions_are_immutable(self):
        paths = workflow_paths()
        self.assertTrue(paths, "workflow privilege guard must inspect at least one workflow")

        for path in paths:
            relative = path.relative_to(ROOT).as_posix()
            text = path.read_text(encoding="utf-8")
            if "pull_request" not in workflow_events(path):
                continue

            for action, ref in external_action_refs(text):
                with self.subTest(workflow=relative, action=action):
                    self.assertRegex(
                        ref,
                        IMMUTABLE_ACTION_REF_RE,
                        f"{relative}: {action}@{ref} must use a full immutable commit SHA "
                        "when untrusted pull-request code can reach the workflow",
                    )

    def test_semantic_trigger_scan_covers_block_scalar_sequence_flow_and_quotes(self):
        fixtures = {
            "block.yml": "on:\n  pull_request:\n  push:\n",
            "scalar.yml": "on: pull_request_target\n",
            "sequence.yml": "on: [push, pull_request]\n",
            "flow.yml": "on: {push: {}, pull_request_target: {}}\n",
            "quoted.yml": "'on':\n  \"pull_request\": {}\n",
        }
        expected = {
            "block.yml": {"pull_request", "push"},
            "scalar.yml": {"pull_request_target"},
            "sequence.yml": {"push", "pull_request"},
            "flow.yml": {"push", "pull_request_target"},
            "quoted.yml": {"pull_request"},
        }

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for name, source in fixtures.items():
                path = root / name
                path.write_text(source, encoding="utf-8")
                with self.subTest(name=name):
                    self.assertEqual(workflow_events(path), expected[name])

    def test_semantic_trigger_scan_fails_closed_on_missing_or_invalid_on_surface(self):
        fixtures = {
            "missing.yml": "name: missing\njobs: {}\n",
            "invalid.yml": "on:\n  - {pull_request: {}}\n",
        }
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for name, source in fixtures.items():
                path = root / name
                path.write_text(source, encoding="utf-8")
                with self.subTest(name=name):
                    with self.assertRaisesRegex(RuntimeError, "workflow"):
                        workflow_events(path)

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

jobs:
  verify:
    steps:
      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1
"""
        self.assertIsNone(SECRET_REF_RE.search(fixture))
        self.assertEqual(write_permissions(fixture), [])
        self.assertEqual(
            external_action_refs(fixture),
            [
                (
                    "actions/checkout",
                    "3d3c42e5aac5ba805825da76410c181273ba90b1",
                )
            ],
        )

    def test_floating_action_fixture_is_detected(self):
        fixture = """on:
  pull_request:

jobs:
  verify:
    steps:
      - uses: actions/checkout@v7
"""
        refs = external_action_refs(fixture)
        self.assertEqual(refs, [("actions/checkout", "v7")])
        self.assertIsNone(IMMUTABLE_ACTION_REF_RE.fullmatch(refs[0][1]))

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
        self.assertEqual(write_permissions(fixture), ["contents"])
        self.assertIsNotNone(SECRET_REF_RE.search(fixture))


if __name__ == "__main__":
    unittest.main()
