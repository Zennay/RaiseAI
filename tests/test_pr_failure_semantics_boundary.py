from functools import lru_cache
import json
from pathlib import Path
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS_DIR = ROOT / ".github" / "workflows"


def workflow_paths(root=ROOT) -> list[Path]:
    workflows = root / ".github" / "workflows"
    return sorted({*workflows.glob("*.yml"), *workflows.glob("*.yaml")})


@lru_cache(maxsize=None)
def failure_semantics_metadata(path: Path) -> dict[str, object]:
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

lookup = lambda do |mapping, target|
  next nil unless mapping.is_a?(Psych::Nodes::Mapping)
  found = nil
  mapping.children.each_slice(2) do |key_node, value_node|
    next unless key_node.is_a?(Psych::Nodes::Scalar) && key_node.value == target
    abort("duplicate #{target} key") if found
    found = value_node
  end
  found
end

events = []
on_node = lookup.call(root, "on")
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

continue_on_error = []
walk = nil
walk = lambda do |node, path|
  case node
  when Psych::Nodes::Mapping
    node.children.each_slice(2) do |key_node, value_node|
      abort("workflow mapping keys must be scalars") unless key_node.is_a?(Psych::Nodes::Scalar)
      child_path = path + [key_node.value]
      if key_node.value == "continue-on-error"
        value =
          if value_node.is_a?(Psych::Nodes::Scalar)
            value_node.value
          else
            "<non-scalar>"
          end
        continue_on_error << {"path" => child_path.join("."), "value" => value}
      end
      walk.call(value_node, child_path)
    end
  when Psych::Nodes::Sequence
    node.children.each_with_index do |child, index|
      walk.call(child, path + [index.to_s])
    end
  end
end
walk.call(root, [])

STDOUT.write(
  JSON.generate(
    {
      "events" => events.uniq.sort,
      "continue_on_error" => continue_on_error,
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
            f"{path}: PR failure-semantics scan failed with exit "
            f"{result.returncode}: "
            f"{result.stderr.decode('utf-8', errors='replace').strip()}"
        )
    return json.loads(result.stdout.decode("utf-8", errors="strict"))


class PullRequestFailureSemanticsBoundaryTests(unittest.TestCase):
    def test_pull_request_workflows_never_allow_best_effort_failures(self):
        inspected = 0

        for path in workflow_paths():
            relative = path.relative_to(ROOT).as_posix()
            metadata = failure_semantics_metadata(path)
            if "pull_request" not in metadata["events"]:
                continue

            inspected += 1
            with self.subTest(workflow=relative):
                self.assertEqual(
                    metadata["continue_on_error"],
                    [],
                    f"{relative}: pull-request validation must fail closed; "
                    "continue-on-error is forbidden at every YAML depth",
                )

        self.assertGreater(
            inspected,
            0,
            "PR failure-semantics boundary must inspect at least one workflow",
        )

    def test_scanner_detects_job_step_expression_and_quoted_key_forms(self):
        fixtures = {
            "job.yml": """on: pull_request
jobs:
  verify:
    continue-on-error: true
    runs-on: ubuntu-24.04
""",
            "step.yml": """on: pull_request
jobs:
  verify:
    runs-on: ubuntu-24.04
    steps:
      - run: exit 1
        continue-on-error: false
""",
            "expression.yml": """on: pull_request
jobs:
  verify:
    runs-on: ubuntu-24.04
    continue-on-error: ${{ matrix.allow_failure }}
""",
            "quoted.yml": """on: pull_request
jobs:
  verify:
    runs-on: ubuntu-24.04
    'continue-on-error': true
""",
        }

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for name, source in fixtures.items():
                path = root / name
                path.write_text(source, encoding="utf-8")
                with self.subTest(name=name):
                    hits = failure_semantics_metadata(path)["continue_on_error"]
                    self.assertEqual(len(hits), 1)

    def test_comments_do_not_create_false_positive_failure_controls(self):
        fixture = """on: pull_request
# continue-on-error: true
jobs:
  verify:
    runs-on: ubuntu-24.04
    steps:
      - run: echo strict
"""
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "workflow.yml"
            path.write_text(fixture, encoding="utf-8")
            metadata = failure_semantics_metadata(path)

        self.assertEqual(metadata["continue_on_error"], [])

    def test_non_pr_workflow_surface_remains_visible_but_outside_pr_rule(self):
        fixture = """on: workflow_dispatch
jobs:
  probe:
    runs-on: ubuntu-24.04
    steps:
      - run: exit 1
        continue-on-error: true
"""
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "workflow.yml"
            path.write_text(fixture, encoding="utf-8")
            metadata = failure_semantics_metadata(path)

        self.assertEqual(metadata["events"], ["workflow_dispatch"])
        self.assertEqual(len(metadata["continue_on_error"]), 1)


if __name__ == "__main__":
    unittest.main()
