import pathlib
import re
import subprocess
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "yaml-surface-contract.yml"
EXPECTED_CRITICAL = {
    ".github/workflows/quality-tooling-test.yml",
    ".github/workflows/watch-app-test.yml",
}


def tracked_yaml_paths():
    raw = subprocess.check_output(["git", "ls-files", "-z"], cwd=ROOT)
    return sorted(
        item
        for item in raw.decode("utf-8").split("\0")
        if item and pathlib.PurePosixPath(item).suffix.lower() in {".yml", ".yaml"}
    )


def parse_yaml_with_psych(path):
    script = r"""
require "psych"
raw = File.binread(ARGV.fetch(0))
raw.force_encoding(Encoding::UTF_8)
abort("#{ARGV.fetch(0)}: invalid UTF-8") unless raw.valid_encoding?
def validate_yaml_tree(node)
  abort("YAML aliases are forbidden") if node.is_a?(Psych::Nodes::Alias)
  if node.respond_to?(:anchor) && node.anchor && !node.anchor.empty?
    abort("YAML anchors are forbidden")
  end

  if node.is_a?(Psych::Nodes::Mapping)
    seen = {}
    node.children.each_slice(2) do |key, value|
      abort("YAML mapping keys must be scalar") unless key.is_a?(Psych::Nodes::Scalar)
      label = key.value
      abort("YAML merge keys are forbidden") if label == "<<"
      abort("duplicate YAML mapping key: #{label}") if seen.key?(label)
      seen[label] = true
      validate_yaml_tree(key)
      validate_yaml_tree(value)
    end
    return
  end

  children = node.respond_to?(:children) ? node.children : nil
  Array(children).each { |child| validate_yaml_tree(child) }
end

tree = Psych.parse_stream(raw)
abort("YAML stream must contain exactly one document") unless tree.children.length == 1
validate_yaml_tree(tree)
"""
    return subprocess.run(
        ["ruby", "--disable-gems", "-e", script, str(path)],
        cwd=ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )


class YamlSurfaceContractTests(unittest.TestCase):
    def setUp(self):
        self.workflow = WORKFLOW.read_text(encoding="utf-8")

    def test_tracked_yaml_surface_is_nonempty_and_includes_critical_workflows(self):
        paths = tracked_yaml_paths()
        self.assertTrue(paths, "tracked YAML discovery must find files")
        self.assertTrue(
            EXPECTED_CRITICAL.issubset(paths),
            f"critical YAML files missing from discovery: {sorted(EXPECTED_CRITICAL - set(paths))}",
        )

    def test_every_tracked_yaml_file_is_regular_utf8_and_syntax_valid(self):
        for relative in tracked_yaml_paths():
            with self.subTest(path=relative):
                path = ROOT / relative
                self.assertFalse(
                    path.is_symlink(),
                    f"{relative} must be a regular repository file, not a symlink",
                )
                self.assertTrue(path.is_file(), f"{relative} must resolve to a regular file")
                path.read_bytes().decode("utf-8")
                parsed = parse_yaml_with_psych(path)
                self.assertEqual(
                    parsed.returncode,
                    0,
                    f"{relative} must parse as YAML: {parsed.stderr}",
                )

    def test_parser_rejects_duplicate_scalar_mapping_keys(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / "duplicate.yml"
            path.write_text(
                "jobs:\n"
                "  verify:\n"
                "    runs-on: ubuntu-24.04\n"
                "    runs-on: self-hosted\n",
                encoding="utf-8",
            )
            parsed = parse_yaml_with_psych(path)
            self.assertNotEqual(parsed.returncode, 0)
            self.assertIn(
                "duplicate YAML mapping key: runs-on",
                parsed.stderr,
            )

    def test_parser_rejects_multiple_yaml_documents(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / "multiple.yml"
            path.write_text(
                "name: primary\n"
                "---\n"
                "name: hidden-secondary\n",
                encoding="utf-8",
            )
            parsed = parse_yaml_with_psych(path)
            self.assertNotEqual(parsed.returncode, 0)
            self.assertIn(
                "YAML stream must contain exactly one document",
                parsed.stderr,
            )

    def test_parser_rejects_non_scalar_mapping_keys(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / "complex-key.yml"
            path.write_text("? [alpha, beta]\n: value\n", encoding="utf-8")
            parsed = parse_yaml_with_psych(path)
            self.assertNotEqual(parsed.returncode, 0)
            self.assertIn(
                "YAML mapping keys must be scalar",
                parsed.stderr,
            )

    def test_parser_rejects_yaml_anchors(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / "anchor.yml"
            path.write_text("defaults: &defaults\n  runner: ubuntu-24.04\n", encoding="utf-8")
            parsed = parse_yaml_with_psych(path)
            self.assertNotEqual(parsed.returncode, 0)
            self.assertIn("YAML anchors are forbidden", parsed.stderr)

    def test_parser_rejects_yaml_aliases(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / "alias.yml"
            path.write_text("copy: *defaults\n", encoding="utf-8")
            parsed = parse_yaml_with_psych(path)
            self.assertNotEqual(parsed.returncode, 0)
            self.assertIn("YAML aliases are forbidden", parsed.stderr)

    def test_parser_rejects_yaml_merge_keys(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / "merge-key.yml"
            path.write_text("job:\n  <<: inherited\n", encoding="utf-8")
            parsed = parse_yaml_with_psych(path)
            self.assertNotEqual(parsed.returncode, 0)
            self.assertIn("YAML merge keys are forbidden", parsed.stderr)

    def _trigger_paths(self, event):
        lines = self.workflow.splitlines()
        start = lines.index(f"  {event}:") + 1
        body = []
        for line in lines[start:]:
            if line and not line.startswith("    "):
                break
            body.append(line)
        self.assertIn("    paths:", body)
        index = body.index("    paths:") + 1
        paths = []
        for line in body[index:]:
            match = re.fullmatch(r'      - "([^"]+)"', line)
            if not match:
                break
            paths.append(match.group(1))
        return paths

    def test_workflow_triggers_cover_current_and_future_yaml_surfaces(self):
        expected = [
            "*.yml",
            "**/*.yml",
            "*.yaml",
            "**/*.yaml",
            "tests/test_yaml_surface_contract.py",
            ".github/workflows/yaml-surface-contract.yml",
        ]
        for event in ("push", "pull_request"):
            with self.subTest(event=event):
                self.assertEqual(self._trigger_paths(event), expected)

    def test_workflow_is_hosted_read_only_exact_head_bounded_and_secret_free(self):
        self.assertIn("runs-on: ubuntu-24.04", self.workflow)
        self.assertNotIn("self-hosted", self.workflow)
        self.assertIn("permissions:\n  contents: read\n", self.workflow)
        self.assertNotRegex(self.workflow, r"\$\{\{\s*secrets\.")
        self.assertNotIn("pull_request_target:", self.workflow)
        self.assertNotIn("continue-on-error: true", self.workflow)
        self.assertIn("timeout-minutes: 5", self.workflow)
        self.assertIn("cancel-in-progress: true", self.workflow)
        expression = (
            "${{ github.event_name == 'pull_request' && "
            "github.event.pull_request.head.sha || github.sha }}"
        )
        self.assertEqual(self.workflow.count(expression), 2)
        self.assertIn("persist-credentials: false", self.workflow)

    def test_workflow_pins_exact_ruby_psych_runtime(self):
        for token in (
            'expected = ["3.2.3", "5.0.1"]',
            "actual = [RUBY_VERSION, Psych::VERSION]",
            "unless actual == expected",
            'unexpected Ruby/Psych runtime:',
        ):
            with self.subTest(token=token):
                self.assertEqual(
                    self.workflow.count(token),
                    1,
                    "YAML parser runtime identity must remain fail-closed and exact",
                )
        self.assertNotIn(
            'abort "Psych unavailable" unless defined?(Psych); puts ',
            self.workflow,
            "runtime probe must not silently accept a different Ruby/Psych version",
        )

    def test_workflow_uses_only_immutable_checkout_action(self):
        refs = re.findall(
            r"^\s*(?:-\s*)?uses:\s*([^@\s]+)@([^\s#]+)",
            self.workflow,
            flags=re.MULTILINE,
        )
        self.assertEqual([action for action, _ in refs], ["actions/checkout"])
        self.assertRegex(refs[0][1], r"^[0-9a-f]{40}$")
        self.assertIn(
            "actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1",
            self.workflow,
        )

    def test_workflow_runs_dynamic_yaml_validation_and_regression(self):
        for token in (
            'subprocess.check_output(["git", "ls-files", "-z"])',
            'pathlib.PurePosixPath(item).suffix.lower() in {".yml", ".yaml"}',
            "candidate.is_symlink()",
            "tracked YAML files must not be symlinks",
            'subprocess.run(["ruby", "--disable-gems", "-e", ruby_parser, path], check=True)',
            "duplicate YAML mapping key",
            "YAML mapping keys must be scalar",
            "YAML anchors are forbidden",
            "YAML aliases are forbidden",
            "YAML merge keys are forbidden",
            "YAML stream must contain exactly one document",
            "python3 -m unittest tests.test_yaml_surface_contract",
            "git diff --exit-code -- .",
            'test -z "$(git ls-files --others --exclude-standard)"',
        ):
            with self.subTest(token=token):
                self.assertIn(token, self.workflow)

    def test_all_run_steps_are_explicit_strict_bash(self):
        lines = self.workflow.splitlines()
        run_indices = [index for index, line in enumerate(lines) if line == "        run: |"]
        self.assertTrue(run_indices)
        step_starts = [
            index for index, line in enumerate(lines) if line.startswith("      - name:")
        ]
        for run_index in run_indices:
            with self.subTest(line=run_index + 1):
                step_start = max(index for index in step_starts if index < run_index)
                following = [index for index in step_starts if index > step_start]
                step_end = min(following) if following else len(lines)
                step = lines[step_start:step_end]
                self.assertIn("        shell: bash", step)
                self.assertEqual(lines[run_index + 1], "          set -euo pipefail")


if __name__ == "__main__":
    unittest.main()
