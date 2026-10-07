import pathlib
import re
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "gradle-bootstrap-integrity.yml"
CHECKOUT_SHA = "3d3c42e5aac5ba805825da76410c181273ba90b1"


class GradleCiRuntimeContractTests(unittest.TestCase):
    def setUp(self):
        self.text = WORKFLOW.read_text(encoding="utf-8")

    def test_runner_and_environment_are_pinned(self):
        self.assertIn("runs-on: ubuntu-24.04", self.text)
        self.assertNotIn("ubuntu-latest", self.text)
        for line in (
            "      LANG: C.UTF-8",
            "      LC_ALL: C.UTF-8",
            '      PYTHONHASHSEED: "1"',
            '      PYTHONDONTWRITEBYTECODE: "1"',
            "      TZ: UTC",
        ):
            with self.subTest(line=line):
                self.assertEqual(self.text.count(line), 1)

    def test_checkout_is_immutable_node24_exact_head(self):
        refs = re.findall(
            r"^\s*(?:-\s*)?uses:\s*([^@\s]+)@([^\s#]+)",
            self.text,
            flags=re.MULTILINE,
        )
        self.assertEqual(refs, [("actions/checkout", CHECKOUT_SHA)])
        self.assertIn(
            f"uses: actions/checkout@{CHECKOUT_SHA} # v7.0.1 (node24)",
            self.text,
        )
        expression = (
            "${{ github.event_name == 'pull_request' && "
            "github.event.pull_request.head.sha || github.sha }}"
        )
        self.assertEqual(self.text.count(f"          ref: {expression}"), 1)
        self.assertEqual(self.text.count("          persist-credentials: false"), 1)

    def test_permissions_are_read_only(self):
        self.assertRegex(
            self.text,
            r"(?ms)^permissions:\n  contents: read\n\nconcurrency:",
        )
        self.assertNotRegex(self.text, r"(?m)^    permissions:")

    def test_all_run_steps_are_strict_bash(self):
        lines = self.text.splitlines()
        step_starts = [
            index for index, line in enumerate(lines)
            if line.startswith("      - name:")
        ]
        run_indices = [
            index for index, line in enumerate(lines)
            if line == "        run: |"
        ]
        self.assertTrue(run_indices)
        for run_index in run_indices:
            with self.subTest(run_line=run_index + 1):
                step_start = max(index for index in step_starts if index < run_index)
                following = [index for index in step_starts if index > step_start]
                step_end = min(following) if following else len(lines)
                step = lines[step_start:step_end]
                self.assertIn("        shell: bash", step)
                self.assertEqual(lines[run_index + 1], "          set -euo pipefail")
        self.assertNotIn("continue-on-error: true", self.text)

    def test_integrity_lane_rejects_repository_side_effects(self):
        self.assertIn("- name: Verify worktree remains clean", self.text)
        for command in (
            "          git diff --exit-code -- .",
            "          git diff --cached --exit-code -- .",
            '          test -z "$(git ls-files --others --exclude-standard)"',
        ):
            with self.subTest(command=command):
                self.assertEqual(self.text.count(command), 1)

    def test_contract_test_is_triggered_and_executed(self):
        path = '      - "tests/test_gradle_ci_runtime_contract.py"'
        self.assertEqual(self.text.count(path), 2)
        self.assertIn(
            "python3 -m unittest tests.test_gradle_bootstrap_integrity tests.test_gradle_ci_runtime_contract",
            self.text,
        )


if __name__ == "__main__":
    unittest.main()
