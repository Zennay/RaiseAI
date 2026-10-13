from functools import lru_cache
import json
from pathlib import Path
import re
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS_DIR = ROOT / ".github" / "workflows"
GITHUB_HOSTED_RUNNER_RE = re.compile(
    r"^(?:ubuntu|windows|macos)-[A-Za-z0-9][A-Za-z0-9._-]*$"
)
SAFE_PR_HEAD_REFS = {
    "${{ github.event.pull_request.head.sha }}",
    "${{ github.event.pull_request.head.sha || github.sha }}",
    "${{ github.event_name == 'pull_request' && github.event.pull_request.head.sha || github.sha }}",
}


def workflow_paths(root=ROOT) -> list[Path]:
    workflows = root / ".github" / "workflows"
    return sorted({*workflows.glob("*.yml"), *workflows.glob("*.yaml")})


@lru_cache(maxsize=None)
def workflow_checkout_metadata(path: Path) -> dict[str, object]:
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

jobs = []
jobs_node = lookup.call(root, "jobs")
if jobs_node
  abort("workflow jobs must be a mapping") unless jobs_node.is_a?(Psych::Nodes::Mapping)
  jobs_node.children.each_slice(2) do |job_name_node, job_node|
    abort("workflow job names must be scalars") unless job_name_node.is_a?(Psych::Nodes::Scalar)
    abort("workflow jobs must be mappings") unless job_node.is_a?(Psych::Nodes::Mapping)

    runs_on_node = lookup.call(job_node, "runs-on")
    runner_labels = []
    case runs_on_node
    when Psych::Nodes::Scalar
      runner_labels << runs_on_node.value
    when Psych::Nodes::Sequence
      runs_on_node.children.each do |runner_node|
        abort("runner labels must be scalars") unless runner_node.is_a?(Psych::Nodes::Scalar)
        runner_labels << runner_node.value
      end
    when nil
      next
    else
      abort("runs-on must be a scalar or sequence")
    end

    checkouts = []
    steps_node = lookup.call(job_node, "steps")
    if steps_node
      abort("job steps must be a sequence") unless steps_node.is_a?(Psych::Nodes::Sequence)
      steps_node.children.each do |step_node|
        abort("workflow steps must be mappings") unless step_node.is_a?(Psych::Nodes::Mapping)
        uses_node = lookup.call(step_node, "uses")
        next unless uses_node.is_a?(Psych::Nodes::Scalar)
        next unless uses_node.value.start_with?("actions/checkout@")

        with_node = lookup.call(step_node, "with")
        inputs = {}
        if with_node
          abort("checkout with must be a mapping") unless with_node.is_a?(Psych::Nodes::Mapping)
          with_node.children.each_slice(2) do |key_node, value_node|
            abort("checkout input names must be scalars") unless key_node.is_a?(Psych::Nodes::Scalar)
            abort("checkout input values must be scalars") unless value_node.is_a?(Psych::Nodes::Scalar)
            abort("duplicate checkout input #{key_node.value}") if inputs.key?(key_node.value)
            inputs[key_node.value] = value_node.value
          end
        end

        checkouts << {"uses" => uses_node.value, "inputs" => inputs}
      end
    end

    jobs << {
      "name" => job_name_node.value,
      "runner_labels" => runner_labels,
      "checkouts" => checkouts,
    }
  end
end

STDOUT.write(JSON.generate({"events" => events.uniq.sort, "jobs" => jobs}))
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
            f"{path}: hosted checkout semantic scan failed with exit "
            f"{result.returncode}: "
            f"{result.stderr.decode('utf-8', errors='replace').strip()}"
        )
    return json.loads(result.stdout.decode("utf-8", errors="strict"))


def github_hosted_jobs(metadata: dict[str, object]) -> list[dict[str, object]]:
    return [
        job
        for job in metadata["jobs"]
        if len(job["runner_labels"]) == 1
        and GITHUB_HOSTED_RUNNER_RE.fullmatch(job["runner_labels"][0])
    ]


class HostedPullRequestCheckoutBoundaryTests(unittest.TestCase):
    def test_hosted_pull_request_checkouts_are_exact_head_and_credential_free(self):
        inspected_checkouts = 0

        for path in workflow_paths():
            relative = path.relative_to(ROOT).as_posix()
            metadata = workflow_checkout_metadata(path)
            if "pull_request" not in metadata["events"]:
                continue

            for job in github_hosted_jobs(metadata):
                for checkout in job["checkouts"]:
                    inspected_checkouts += 1
                    inputs = checkout["inputs"]
                    with self.subTest(workflow=relative, job=job["name"]):
                        self.assertEqual(
                            inputs.get("persist-credentials"),
                            "false",
                            f"{relative}:{job['name']}: hosted PR checkout must disable "
                            "persisted GitHub credentials",
                        )
                        self.assertIn(
                            inputs.get("ref"),
                            SAFE_PR_HEAD_REFS,
                            f"{relative}:{job['name']}: hosted PR checkout must select "
                            "the exact source PR head rather than the synthetic merge ref",
                        )

        self.assertGreater(
            inspected_checkouts,
            0,
            "hosted PR checkout boundary must inspect at least one checkout step",
        )

    def test_scanner_extracts_checkout_inputs_without_matching_other_actions(self):
        fixture = """on: pull_request
jobs:
  verify:
    runs-on: ubuntu-24.04
    steps:
      - uses: owner/other@0123456789012345678901234567890123456789
        with:
          ref: ignored
      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1
        with:
          ref: ${{ github.event.pull_request.head.sha }}
          persist-credentials: false
"""
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "workflow.yml"
            path.write_text(fixture, encoding="utf-8")
            metadata = workflow_checkout_metadata(path)

        jobs = github_hosted_jobs(metadata)
        self.assertEqual(len(jobs), 1)
        self.assertEqual(len(jobs[0]["checkouts"]), 1)
        checkout = jobs[0]["checkouts"][0]
        self.assertEqual(
            checkout["inputs"]["ref"],
            "${{ github.event.pull_request.head.sha }}",
        )
        self.assertEqual(checkout["inputs"]["persist-credentials"], "false")

    def test_missing_ref_or_persist_credentials_stays_visible_to_boundary(self):
        fixture = """on:
  pull_request:
jobs:
  verify:
    runs-on: windows-2025
    steps:
      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1
"""
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "workflow.yml"
            path.write_text(fixture, encoding="utf-8")
            metadata = workflow_checkout_metadata(path)

        checkout = github_hosted_jobs(metadata)[0]["checkouts"][0]
        self.assertNotIn("ref", checkout["inputs"])
        self.assertNotIn("persist-credentials", checkout["inputs"])


if __name__ == "__main__":
    unittest.main()
