"""Reject attacker-controlled GitHub event interpolation in workflow shell commands.

GitHub renders expressions before invoking the shell. Values from PR titles,
fork branch names, issue comments or workflow inputs must be passed through
step env instead of inserted directly into run scripts.

Quality-only: this does not modify Watch runtime or physical acceptance.
"""

import json
from pathlib import Path
import re
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
EXPRESSION = re.compile(r"\$\{\{(.*?)\}\}", flags=re.DOTALL)
BRACKET_FIELD = re.compile(r"\[\s*(['\"])([a-z_][a-z_0-9]*)\1\s*\]", re.I)
UNTRUSTED = (
    "github.head_ref",
    "github.event.pull_request.title",
    "github.event.pull_request.body",
    "github.event.pull_request.head.ref",
    "github.event.pull_request.head.label",
    "github.event.issue.title",
    "github.event.issue.body",
    "github.event.comment.body",
    "github.event.discussion.title",
    "github.event.discussion.body",
    "github.event.review.body",
    "github.event.workflow_dispatch.inputs",
    "github.event.inputs",
    "github.event.workflow_run.head_branch",
    "github.event.workflow_run.display_title",
    "github.event.release.name",
    "github.event.release.body",
    "github.event.release.tag_name",
    "github.ref_name",
    "github.event.client_payload",
    "inputs.",
)

# Parse YAML semantically rather than grep lines: block and quoted run values
# must be checked, whereas YAML comments and env values are not shell code.
RUBY = r'''
require "json"
require "psych"
raw = File.binread(ARGV.fetch(0))
raw.force_encoding(Encoding::UTF_8)
abort("workflow must use valid UTF-8") unless raw.valid_encoding?
stream = Psych.parse_stream(raw)
abort("workflow must contain one YAML document") unless stream.children.length == 1
root = stream.children.fetch(0).root
abort("workflow root must be a mapping") unless root.is_a?(Psych::Nodes::Mapping)
lookup = lambda do |mapping, name|
  abort("expected a mapping") unless mapping.is_a?(Psych::Nodes::Mapping)
  found = nil
  mapping.children.each_slice(2) do |key, value|
    next unless key.is_a?(Psych::Nodes::Scalar) && key.value == name
    abort("duplicate #{name} key") unless found.nil?
    found = value
  end
  found
end
jobs = lookup.call(root, "jobs")
abort("jobs must be a mapping") unless jobs.is_a?(Psych::Nodes::Mapping)
commands = []
jobs.children.each_slice(2) do |name, job|
  abort("job name must be a scalar") unless name.is_a?(Psych::Nodes::Scalar)
  abort("job must be a mapping") unless job.is_a?(Psych::Nodes::Mapping)
  steps = lookup.call(job, "steps")
  next if steps.nil?
  abort("steps must be a sequence") unless steps.is_a?(Psych::Nodes::Sequence)
  steps.children.each_with_index do |step, index|
    abort("step must be a mapping") unless step.is_a?(Psych::Nodes::Mapping)
    run = lookup.call(step, "run")
    next if run.nil?
    abort("run must be a scalar") unless run.is_a?(Psych::Nodes::Scalar)
    commands << {"job" => name.value, "step" => index, "run" => run.value}
  end
end
STDOUT.write(JSON.generate(commands))
'''


def workflow_paths(root: Path = ROOT) -> list[Path]:
    parent = root / ".github" / "workflows"
    return sorted({*parent.glob("*.yml"), *parent.glob("*.yaml")})


def run_steps(path: Path) -> list[dict[str, object]]:
    result = subprocess.run(
        ["ruby", "--disable-gems", "-e", RUBY, str(path)],
        cwd=ROOT,
        capture_output=True,
        timeout=15,
        check=False,
    )
    if result.returncode:
        raise ValueError(
            f"{path}: invalid workflow YAML: "
            f"{result.stderr.decode('utf-8', 'replace').strip()}"
        )
    return json.loads(result.stdout.decode("utf-8", "strict"))


def unsafe_run_expressions(command: str) -> list[str]:
    dangerous = []
    for expression in EXPRESSION.findall(command):
        normalized = BRACKET_FIELD.sub(
            lambda match: "." + match.group(2), expression
        )
        normalized = re.sub(r"\s+", "", normalized).lower()
        for reference in UNTRUSTED:
            suffix = "" if reference.endswith(".") else r"(?=[^a-z0-9_]|$)"
            if re.search(
                r"(?<![a-z0-9_])" + re.escape(reference) + suffix, normalized
            ):
                dangerous.append(expression.strip())
                break
        else:
            # The whole payload contains free-form user text as well.
            for reference in (
                "github.event.pull_request",
                "github.event.issue",
                "github.event.comment",
            ):
                if re.search(
                    r"(?<![a-z0-9_])" + re.escape(reference) + r"(?=[),}]|$)",
                    normalized,
                ):
                    dangerous.append(expression.strip())
                    break
    return list(dict.fromkeys(dangerous))


class WorkflowUntrustedRunInterpolationTests(unittest.TestCase):
    def test_repository_workflow_run_steps_do_not_interpolate_untrusted_text(self):
        paths = workflow_paths()
        self.assertTrue(paths, "workflow inventory must not disappear")
        checked = 0
        for path in paths:
            for step in run_steps(path):
                with self.subTest(workflow=path.name, job=step["job"], step=step["step"]):
                    checked += 1
                    unsafe = unsafe_run_expressions(str(step["run"]))
                    self.assertFalse(
                        unsafe,
                        f"{path.name} injects untrusted expressions into shell: "
                        f"{unsafe}; use a step env variable instead",
                    )
        self.assertGreater(checked, 0, "workflow run inventory must not be empty")

    def test_rejects_common_event_and_bracket_notation_injection(self):
        samples = (
            "echo '${{ github.head_ref }}'",
            "echo '${{ github.event.pull_request.title }}'",
            "echo '${{ github.event.pull_request.body }}'",
            "echo '${{ github.event.pull_request.head.ref }}'",
            "echo '${{ github.event.issue.title }}'",
            "echo '${{ github.event.comment.body }}'",
            "echo '${{ github.event.workflow_dispatch.inputs.choice }}'",
            "echo '${{ github.event.client_payload.name }}'",
            "echo '${{ github.event.inputs.target }}'",
            "echo '${{ github.event.workflow_run.head_branch }}'",
            "echo '${{ github.event.workflow_run.display_title }}'",
            "echo '${{ github.event.release.name }}'",
            "echo '${{ github.event.release.body }}'",
            "echo '${{ github.event.release.tag_name }}'",
            "echo '${{ github.ref_name }}'",
            "echo '${{ inputs.target }}'",
            "echo '${{ format('{0}', github.event.discussion.body) }}'",
            'echo "${{ github[\'event\'][\'pull_request\'][\'title\'] }}"',
            "echo '${{ toJSON(github.event.pull_request) }}'",
        )
        for sample in samples:
            with self.subTest(sample=sample):
                self.assertTrue(unsafe_run_expressions(sample))

    def test_allows_verified_sha_and_inert_shell_env_values(self):
        samples = (
            'echo "${{ github.sha }}"',
            'echo "${{ github.event.pull_request.head.sha }}"',
            'echo "${{ github.repository }}"',
            'echo "${{ github.event.pull_request.number }}"',
            'printf "%s\n" "$SAFE_TITLE"',
        )
        for sample in samples:
            with self.subTest(sample=sample):
                self.assertEqual(unsafe_run_expressions(sample), [])

    def test_semantic_run_extractor_handles_yaml_block_quoted_and_comments(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "workflow.yml"
            path.write_text(
                "on: pull_request\njobs:\n  checks:\n    steps:\n"
                "      - run: 'echo ${{ github.head_ref }}'\n"
                "      - run: |\n          echo '${{ github.event.comment.body }}'\n"
                "      - uses: actions/checkout@123\n"
                "  reusable:\n    uses: org/repo/.github/workflows/other.yml@main\n"
                "# run: ${{ github.event.pull_request.title }}\n",
                encoding="utf-8",
            )
            steps = run_steps(path)
            self.assertEqual(len(steps), 2)
            self.assertTrue(all(unsafe_run_expressions(str(s["run"])) for s in steps))

    def test_duplicate_run_and_invalid_utf8_fail_closed(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "workflow.yml"
            path.write_text(
                "jobs:\n  check:\n    steps:\n"
                "      - run: echo hello\n        run: echo ignored\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "duplicate run key"):
                run_steps(path)
            path.write_bytes(b"jobs: \xff\n")
            with self.assertRaisesRegex(ValueError, "valid UTF-8"):
                run_steps(path)


if __name__ == "__main__":
    unittest.main()
