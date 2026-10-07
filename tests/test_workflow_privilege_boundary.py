from functools import lru_cache
import json
from pathlib import Path
import re
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS_DIR = ROOT / ".github" / "workflows"
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
jobs_node = nil
root.children.each_slice(2) do |key_node, value_node|
  next unless key_node.is_a?(Psych::Nodes::Scalar)
  if key_node.value == "on"
    abort("workflow must declare on exactly once") if on_node
    on_node = value_node
  elsif key_node.value == "jobs"
    abort("workflow must declare jobs exactly once") if jobs_node
    jobs_node = value_node
  end
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

environments = []
external_actions = []
if jobs_node
  abort("workflow jobs must be a mapping") unless jobs_node.is_a?(Psych::Nodes::Mapping)
  jobs_node.children.each_slice(2) do |job_name_node, job_node|
    abort("workflow job names must be scalars") unless job_name_node.is_a?(Psych::Nodes::Scalar)
    abort("workflow jobs must be mappings") unless job_node.is_a?(Psych::Nodes::Mapping)
    job_node.children.each_slice(2) do |key_node, value_node|
      next unless key_node.is_a?(Psych::Nodes::Scalar)
      environments << job_name_node.value if key_node.value == "environment"
      if key_node.value == "uses"
        abort("workflow uses values must be scalars") unless value_node.is_a?(Psych::Nodes::Scalar)
        external_actions << value_node.value
      end
      next unless key_node.value == "steps"
      abort("workflow steps must be a sequence") unless value_node.is_a?(Psych::Nodes::Sequence)
      value_node.children.each do |step_node|
        abort("workflow steps must be mappings") unless step_node.is_a?(Psych::Nodes::Mapping)
        step_node.children.each_slice(2) do |step_key_node, step_value_node|
          next unless step_key_node.is_a?(Psych::Nodes::Scalar) && step_key_node.value == "uses"
          abort("workflow uses values must be scalars") unless step_value_node.is_a?(Psych::Nodes::Scalar)
          external_actions << step_value_node.value
        end
      end
    end
  end
end

writes = []
secret_expressions = []
inherited_secrets = []
walk = nil
walk = lambda do |node|
  if node.is_a?(Psych::Nodes::Scalar)
    if node.value.match?(/\$\{\{[^}\n]*\bsecrets\b/)
      secret_expressions << node.value
    end
    return
  end

  if node.is_a?(Psych::Nodes::Mapping)
    node.children.each_slice(2) do |key_node, value_node|
      if key_node.is_a?(Psych::Nodes::Scalar) && key_node.value == "secrets"
        if value_node.is_a?(Psych::Nodes::Scalar) && value_node.value == "inherit"
          inherited_secrets << "inherit"
        end
      end
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

STDOUT.write(
  JSON.generate(
    {
      "events" => events.uniq.sort,
      "writes" => writes,
      "secret_expressions" => secret_expressions,
      "inherited_secrets" => inherited_secrets,
      "external_actions" => external_actions,
      "environments" => environments,
    }
  )
)
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


def external_action_refs(path: Path) -> list[tuple[str, str]]:
    refs = []
    for uses in workflow_security_metadata(path)["external_actions"]:
        if uses.startswith("./") or uses.startswith("docker://"):
            continue
        action, separator, ref = uses.rpartition("@")
        if not separator:
            refs.append((uses, ""))
            continue
        refs.append((action, ref))
    return refs


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

    def test_pull_request_workflows_cannot_receive_privileged_context(self):
        paths = workflow_paths()
        self.assertTrue(paths, "workflow privilege guard must inspect at least one workflow")

        for path in paths:
            relative = path.relative_to(ROOT).as_posix()
            metadata = workflow_security_metadata(path)
            if "pull_request" not in metadata["events"]:
                continue

            with self.subTest(workflow=relative):
                self.assertEqual(
                    metadata["secret_expressions"],
                    [],
                    f"{relative}: pull_request workflows must not consume repository "
                    "or environment secrets",
                )
                self.assertEqual(
                    metadata["writes"],
                    [],
                    f"{relative}: pull_request workflows must not receive write token permissions",
                )
                self.assertEqual(
                    metadata["inherited_secrets"],
                    [],
                    f"{relative}: pull_request workflows must not inherit repository secrets into reusable workflows",
                )
                self.assertEqual(
                    metadata["environments"],
                    [],
                    f"{relative}: pull_request workflows must not bind deployment environments",
                )

    def test_pull_request_external_actions_are_immutable(self):
        paths = workflow_paths()
        self.assertTrue(paths, "workflow privilege guard must inspect at least one workflow")

        for path in paths:
            relative = path.relative_to(ROOT).as_posix()
            metadata = workflow_security_metadata(path)
            if "pull_request" not in metadata["events"]:
                continue

            for action, ref in external_action_refs(path):
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

    def test_secret_scan_is_semantic_and_covers_expression_variants(self):
        fixtures = {
            "dot.yml": 'on: push\nenv: {TOKEN: "${{ secrets.API_TOKEN }}"}\n',
            "bracket.yml": "on: push\nenv: {TOKEN: \"${{secrets['API_TOKEN']}}\"}\n",
            "whole.yml": 'on: push\nenv: {BLOB: "${{ toJSON(secrets) }}"}\n',
            "comment.yml": "on: push\n# ${{ secrets.COMMENT_ONLY }}\nenv: {VALUE: \"${{ vars.PUBLIC_VALUE }}\"}\n",
        }
        expected_counts = {
            "dot.yml": 1,
            "bracket.yml": 1,
            "whole.yml": 1,
            "comment.yml": 0,
        }

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for name, source in fixtures.items():
                path = root / name
                path.write_text(source, encoding="utf-8")
                with self.subTest(name=name):
                    self.assertEqual(
                        len(workflow_security_metadata(path)["secret_expressions"]),
                        expected_counts[name],
                    )

    def test_secret_inheritance_scan_is_semantic(self):
        fixtures = {
            "block.yml": "on: pull_request\njobs:\n  call:\n    uses: ./.github/workflows/reuse.yml\n    secrets: inherit\n",
            "quoted.yml": "on: pull_request\njobs:\n  call:\n    uses: ./.github/workflows/reuse.yml\n    'secrets': 'inherit'\n",
            "flow.yml": "on: pull_request\njobs: {call: {uses: ./.github/workflows/reuse.yml, secrets: inherit}}\n",
            "mapped.yml": "on: pull_request\njobs:\n  call:\n    uses: ./.github/workflows/reuse.yml\n    secrets: {TOKEN: public-placeholder}\n",
        }
        expected_counts = {
            "block.yml": 1,
            "quoted.yml": 1,
            "flow.yml": 1,
            "mapped.yml": 0,
        }

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for name, source in fixtures.items():
                path = root / name
                path.write_text(source, encoding="utf-8")
                with self.subTest(name=name):
                    self.assertEqual(
                        len(workflow_security_metadata(path)["inherited_secrets"]),
                        expected_counts[name],
                    )

    def test_deployment_environment_scan_is_job_scoped(self):
        fixtures = {
            "scalar.yml": "on: push\njobs:\n  deploy:\n    environment: production\n    runs-on: ubuntu-24.04\n",
            "mapping.yml": "on: push\njobs: {deploy: {environment: {name: production}, runs-on: ubuntu-24.04}}\n",
            "action-input.yml": "on: push\njobs:\n  test:\n    runs-on: ubuntu-24.04\n    steps:\n      - uses: owner/action@0123456789012345678901234567890123456789\n        with:\n          environment: test\n",
        }
        expected = {
            "scalar.yml": ["deploy"],
            "mapping.yml": ["deploy"],
            "action-input.yml": [],
        }

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for name, source in fixtures.items():
                path = root / name
                path.write_text(source, encoding="utf-8")
                with self.subTest(name=name):
                    self.assertEqual(
                        workflow_security_metadata(path)["environments"],
                        expected[name],
                    )

    def test_semantic_scan_fails_closed_on_missing_or_invalid_security_surface(self):
        fixtures = {
            "missing-on.yml": "name: missing\njobs: {}\n",
            "invalid-on.yml": "on:\n  - {pull_request: {}}\n",
            "invalid-permissions.yml": "on: push\npermissions: [contents, read]\n",
            "invalid-uses.yml": "on: pull_request\njobs: {test: {steps: [{uses: {repo: action}}]}}\n",
        }
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for name, source in fixtures.items():
                path = root / name
                path.write_text(source, encoding="utf-8")
                with self.subTest(name=name):
                    with self.assertRaisesRegex(RuntimeError, "workflow security"):
                        workflow_security_metadata(path)

    def test_semantic_external_action_scan_covers_quotes_flow_and_comments(self):
        sha = "3d3c42e5aac5ba805825da76410c181273ba90b1"
        fixtures = {
            "block.yml": (
                "on: pull_request\njobs:\n  verify:\n    steps:\n"
                f"      - uses: actions/checkout@{sha}\n"
            ),
            "quoted.yml": (
                "on: pull_request\njobs:\n  verify:\n    steps:\n"
                f"      - 'uses': \"actions/checkout@{sha}\" # pinned\n"
            ),
            "flow.yml": (
                "on: pull_request\njobs: {verify: {steps: "
                f"[{{uses: actions/checkout@{sha}}}]}}}}\n"
            ),
            "reusable.yml": (
                "on: pull_request\njobs:\n  verify:\n"
                f"    uses: owner/repo/.github/workflows/reuse.yml@{sha}\n"
            ),
            "local.yml": (
                "on: pull_request\njobs: {verify: {steps: "
                "[{uses: ./.github/actions/local-check}]}}\n"
            ),
            "docker.yml": (
                "on: pull_request\njobs: {verify: {steps: "
                "[{uses: docker://alpine:3.20}]}}\n"
            ),
            "env-uses.yml": (
                "on: pull_request\njobs: {verify: {env: "
                "{uses: owner/action@v1}, steps: [{run: echo safe}]}}\n"
            ),
            "comment.yml": (
                "on: pull_request\njobs:\n  verify:\n    steps:\n"
                "      # uses: owner/action@v1\n"
                "      - run: echo safe\n"
            ),
        }
        expected = {
            "block.yml": [("actions/checkout", sha)],
            "quoted.yml": [("actions/checkout", sha)],
            "flow.yml": [("actions/checkout", sha)],
            "reusable.yml": [("owner/repo/.github/workflows/reuse.yml", sha)],
            "local.yml": [],
            "docker.yml": [],
            "env-uses.yml": [],
            "comment.yml": [],
        }

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for name, source in fixtures.items():
                path = root / name
                path.write_text(source, encoding="utf-8")
                with self.subTest(name=name):
                    self.assertEqual(external_action_refs(path), expected[name])

    def test_unversioned_external_action_fixture_is_detected(self):
        fixture = """on: pull_request
jobs:
  verify:
    steps:
      - uses: owner/action
"""
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "unversioned.yml"
            path.write_text(fixture, encoding="utf-8")
            refs = external_action_refs(path)

        self.assertEqual(refs, [("owner/action", "")])
        self.assertIsNone(IMMUTABLE_ACTION_REF_RE.fullmatch(refs[0][1]))

    def test_floating_external_action_fixture_is_detected(self):
        fixture = """on: pull_request
jobs:
  verify:
    steps:
      - "uses": "actions/checkout@v7"
"""
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "floating.yml"
            path.write_text(fixture, encoding="utf-8")
            refs = external_action_refs(path)

        self.assertEqual(refs, [("actions/checkout", "v7")])
        self.assertIsNone(IMMUTABLE_ACTION_REF_RE.fullmatch(refs[0][1]))


if __name__ == "__main__":
    unittest.main()
