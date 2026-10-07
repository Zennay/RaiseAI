from functools import lru_cache
import json
from pathlib import Path
import re
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS_DIR = ROOT / ".github" / "workflows"
SECRET_REF_RE = re.compile(r"\$\{\{[^}\n]*\bsecrets\b")
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


@lru_cache(maxsize=None)
def workflow_security_metadata(path: Path) -> dict[str, object]:
    script = r"""
require "json"
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

writes = []
walk = nil
walk = lambda do |node|
  if node.is_a?(Psych::Nodes::Mapping)
    node.children.each_slice(2) do |key_node, value_node|
      if key_node.is_a?(Psych::Nodes::Scalar) && key_node.value == "permissions"
        case value_node
        when Psych::Nodes::Scalar
          writes << "write-all" if value_node.value == "write-all"
        when Psych::Nodes::Mapping
          value_node.children.each_slice(2) do |permission_node, level_node|
            abort("permission names must be scalars") unless permission_node.is_a?(Psych::Nodes::Scalar)
            abort("permission levels must be scalars") unless level_node.is_a?(Psych::Nodes::Scalar)
            writes << permission_node.value if level_node.value == "write"
          end
        else
          abort("permissions must be a scalar or mapping")
        end
      end
      walk.call(value_node)
    end
    return
  end
  children = node.respond_to?(:children) ? node.children : nil
  Array(children).each { |child| walk.call(child) }
end
walk.call(root)

STDOUT.write(JSON.generate({"events" => events.uniq.sort, "writes" => writes}))
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
            f"{path}: workflow security semantic scan failed with exit "
            f"{result.returncode}: "
            f"{result.stderr.decode('utf-8', errors='replace').strip()}"
        )
    return json.loads(result.stdout.decode("utf-8", errors="strict"))


def external_action_refs(text: str) -> list[tuple[str, str]]:
    return EXTERNAL_ACTION_RE.findall(text)


class WorkflowPrivilegeBoundaryTests(unittest.TestCase):
    def test_pull_request_target_is_forbidden_repository_wide(self):
        paths = workflow_paths()
        self.assertTrue(paths, "workflow privilege guard must inspect at least one workflow")

        for path in paths:
            relative = path.relative_to(ROOT).as_posix()
            with self.subTest(workflow=relative):
                metadata = workflow_security_metadata(path)
                self.assertNotIn(
                    "pull_request_target",
                    metadata["events"],
                    f"{relative}: pull_request_target is forbidden because it executes "
                    "untrusted PR context with base-repository privileges",
                )

    def test_pull_request_workflows_cannot_receive_secrets_or_write_permissions(self):
        paths = workflow_paths()
        self.assertTrue(paths, "workflow privilege guard must inspect at least one workflow")

        for path in paths:
            relative = path.relative_to(ROOT).as_posix()
            text = path.read_text(encoding="utf-8")
            metadata = workflow_security_metadata(path)
            if "pull_request" not in metadata["events"]:
                continue

            with self.subTest(workflow=relative):
                self.assertIsNone(
                    SECRET_REF_RE.search(text),
                    f"{relative}: pull_request workflows must not consume repository secrets",
                )
                self.assertEqual(
                    metadata["writes"],
                    [],
                    f"{relative}: pull_request workflows must not receive write token permissions",
                )

    def test_pull_request_external_actions_are_immutable(self):
        paths = workflow_paths()
        self.assertTrue(paths, "workflow privilege guard must inspect at least one workflow")

        for path in paths:
            relative = path.relative_to(ROOT).as_posix()
            text = path.read_text(encoding="utf-8")
            metadata = workflow_security_metadata(path)
            if "pull_request" not in metadata["events"]:
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
                    metadata = workflow_security_metadata(path)
                    self.assertEqual(set(metadata["events"]), expected[name])

    def test_semantic_permission_scan_covers_block_flow_quotes_and_write_all(self):
        fixtures = {
            "block.yml": "on: push\npermissions:\n  contents: write\n",
            "flow.yml": "on: push\npermissions: {checks: write, contents: read}\n",
            "quoted.yml": "on: push\n'permissions': {\"statuses\": \"write\"}\n",
            "write-all.yml": "on: push\npermissions: write-all\n",
            "read-only.yml": "on: push\npermissions: {contents: read}\n",
        }
        expected = {
            "block.yml": ["contents"],
            "flow.yml": ["checks"],
            "quoted.yml": ["statuses"],
            "write-all.yml": ["write-all"],
            "read-only.yml": [],
        }

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for name, source in fixtures.items():
                path = root / name
                path.write_text(source, encoding="utf-8")
                with self.subTest(name=name):
                    self.assertEqual(
                        workflow_security_metadata(path)["writes"],
                        expected[name],
                    )

    def test_semantic_scan_fails_closed_on_missing_or_invalid_security_surface(self):
        fixtures = {
            "missing-on.yml": "name: missing\njobs: {}\n",
            "invalid-on.yml": "on:\n  - {pull_request: {}}\n",
            "invalid-permissions.yml": "on: push\npermissions: [contents, read]\n",
        }
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for name, source in fixtures.items():
                path = root / name
                path.write_text(source, encoding="utf-8")
                with self.subTest(name=name):
                    with self.assertRaisesRegex(RuntimeError, "workflow security"):
                        workflow_security_metadata(path)

    def test_secret_namespace_guard_covers_dot_bracket_and_whole_object_forms(self):
        for expression in (
            "${{ secrets.API_TOKEN }}",
            "${{secrets['API_TOKEN']}}",
            "${{ toJSON(secrets) }}",
        ):
            with self.subTest(expression=expression):
                self.assertIsNotNone(SECRET_REF_RE.search(expression))
        self.assertIsNone(SECRET_REF_RE.search("${{ vars.PUBLIC_VALUE }}"))

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

    def test_privileged_manual_fixture_secret_reference_is_detected(self):
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
        self.assertIsNotNone(SECRET_REF_RE.search(fixture))


if __name__ == "__main__":
    unittest.main()
