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


def workflow_paths(root=ROOT) -> list[Path]:
    workflows = root / ".github" / "workflows"
    return sorted({*workflows.glob("*.yml"), *workflows.glob("*.yaml")})


@lru_cache(maxsize=None)
def hosted_pr_metadata(path: Path) -> dict[str, object]:
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

top_permissions = nil
permissions_node = lookup.call(root, "permissions")
case permissions_node
when Psych::Nodes::Mapping
  top_permissions = {}
  permissions_node.children.each_slice(2) do |name_node, level_node|
    abort("permission names must be scalars") unless name_node.is_a?(Psych::Nodes::Scalar)
    abort("permission levels must be scalars") unless level_node.is_a?(Psych::Nodes::Scalar)
    abort("duplicate permission #{name_node.value}") if top_permissions.key?(name_node.value)
    top_permissions[name_node.value] = level_node.value
  end
when Psych::Nodes::Scalar
  top_permissions = permissions_node.value
when nil
  top_permissions = nil
else
  abort("workflow permissions must be a scalar or mapping")
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

    timeout_node = lookup.call(job_node, "timeout-minutes")
    timeout = nil
    if timeout_node
      abort("timeout-minutes must be a scalar") unless timeout_node.is_a?(Psych::Nodes::Scalar)
      timeout = timeout_node.value
    end

    job_permissions_node = lookup.call(job_node, "permissions")
    job_permissions = !job_permissions_node.nil?

    jobs << {
      "name" => job_name_node.value,
      "runner_labels" => runner_labels,
      "timeout" => timeout,
      "job_permissions" => job_permissions,
    }
  end
end

STDOUT.write(
  JSON.generate(
    {
      "events" => events.uniq.sort,
      "top_permissions" => top_permissions,
      "jobs" => jobs,
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
            f"{path}: hosted PR workflow semantic scan failed with exit "
            f"{result.returncode}: "
            f"{result.stderr.decode('utf-8', errors='replace').strip()}"
        )
    return json.loads(result.stdout.decode("utf-8", errors="strict"))


def github_hosted_jobs(metadata: dict[str, object]) -> list[dict[str, object]]:
    jobs = []
    for job in metadata["jobs"]:
        labels = job["runner_labels"]
        if len(labels) == 1 and GITHUB_HOSTED_RUNNER_RE.fullmatch(labels[0]):
            jobs.append(job)
    return jobs


class HostedPullRequestWorkflowBoundaryTests(unittest.TestCase):
    def test_hosted_pull_request_workflows_are_explicitly_read_only_and_bounded(self):
        inspected_jobs = 0

        for path in workflow_paths():
            relative = path.relative_to(ROOT).as_posix()
            metadata = hosted_pr_metadata(path)
            if "pull_request" not in metadata["events"]:
                continue

            hosted_jobs = github_hosted_jobs(metadata)
            if not hosted_jobs:
                continue

            inspected_jobs += len(hosted_jobs)
            with self.subTest(workflow=relative):
                self.assertEqual(
                    metadata["top_permissions"],
                    {"contents": "read"},
                    f"{relative}: hosted pull-request workflows must explicitly scope "
                    "the token to contents: read only",
                )

            for job in hosted_jobs:
                with self.subTest(workflow=relative, job=job["name"]):
                    self.assertFalse(
                        job["job_permissions"],
                        f"{relative}:{job['name']}: hosted pull-request jobs must not "
                        "override token permissions",
                    )
                    self.assertIsNotNone(
                        job["timeout"],
                        f"{relative}:{job['name']}: hosted pull-request jobs need an "
                        "explicit timeout-minutes budget",
                    )
                    try:
                        timeout = int(job["timeout"])
                    except (TypeError, ValueError):
                        self.fail(
                            f"{relative}:{job['name']}: timeout-minutes must be a "
                            f"literal integer, got {job['timeout']!r}"
                        )
                    self.assertGreaterEqual(
                        timeout,
                        1,
                        f"{relative}:{job['name']}: timeout-minutes must be positive",
                    )
                    self.assertLessEqual(
                        timeout,
                        30,
                        f"{relative}:{job['name']}: hosted PR validation must stay "
                        "within a 30-minute hard budget",
                    )

        self.assertGreater(
            inspected_jobs,
            0,
            "hosted PR boundary must inspect at least one GitHub-hosted PR job",
        )

    def test_semantic_scanner_distinguishes_hosted_and_self_hosted_jobs(self):
        fixture = """on: [push, pull_request]
permissions: {contents: read}
jobs:
  hosted:
    runs-on: ubuntu-24.04
    timeout-minutes: 5
  self:
    runs-on: [self-hosted, vps-bb300bba]
    timeout-minutes: 30
"""
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "workflow.yml"
            path.write_text(fixture, encoding="utf-8")
            metadata = hosted_pr_metadata(path)

        self.assertEqual(set(metadata["events"]), {"push", "pull_request"})
        self.assertEqual(metadata["top_permissions"], {"contents": "read"})
        self.assertEqual(
            [job["name"] for job in github_hosted_jobs(metadata)],
            ["hosted"],
        )

    def test_semantic_scanner_exposes_permission_override_and_timeout_shapes(self):
        fixture = """on:
  pull_request:
permissions:
  contents: read
jobs:
  verify:
    runs-on: macos-15
    timeout-minutes: 12
    permissions:
      contents: read
"""
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "workflow.yml"
            path.write_text(fixture, encoding="utf-8")
            metadata = hosted_pr_metadata(path)

        jobs = github_hosted_jobs(metadata)
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0]["timeout"], "12")
        self.assertTrue(jobs[0]["job_permissions"])

    def test_hosted_runner_classifier_rejects_expressions_and_self_hosted_labels(self):
        fixtures = [
            {"runner_labels": ["ubuntu-24.04"]},
            {"runner_labels": ["windows-2025"]},
            {"runner_labels": ["macos-15"]},
        ]
        for job in fixtures:
            metadata = {"jobs": [{**job, "name": "verify"}]}
            self.assertEqual(len(github_hosted_jobs(metadata)), 1)

        for labels in (
            ["self-hosted", "vps-bb300bba"],
            ["${{ matrix.runner }}"],
            ["ubuntu-latest", "extra-label"],
        ):
            metadata = {"jobs": [{"name": "verify", "runner_labels": labels}]}
            self.assertEqual(github_hosted_jobs(metadata), [])


    def test_semantic_scanner_keeps_read_all_distinct_from_exact_read_only(self):
        fixture = """on: pull_request
permissions: read-all
jobs:
  verify:
    runs-on: ubuntu-24.04
    timeout-minutes: 5
"""
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "workflow.yml"
            path.write_text(fixture, encoding="utf-8")
            metadata = hosted_pr_metadata(path)

        self.assertEqual(metadata["top_permissions"], "read-all")
        self.assertNotEqual(metadata["top_permissions"], {"contents": "read"})


if __name__ == "__main__":
    unittest.main()
