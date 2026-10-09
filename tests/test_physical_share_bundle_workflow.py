from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = (ROOT / ".github" / "workflows" / "physical-share-bundle-quality.yml").read_text(
    encoding="utf-8"
)


class PhysicalShareBundleWorkflowContractTests(unittest.TestCase):
    def test_workflow_is_exact_head_vps_bound_and_read_only(self):
        self.assertEqual(WORKFLOW.count("    runs-on: [self-hosted, linux, x64, vps-bb300bba]"), 1)
        self.assertEqual(WORKFLOW.count('          test "$(hostname)" = "vps-bb300bba"'), 1)
        self.assertEqual(WORKFLOW.count('          test "${RUNNER_NAME:-}" = "vps-bb300bba"'), 1)
        self.assertIn("permissions:\n  contents: read\n", WORKFLOW)
        self.assertNotRegex(WORKFLOW, r"(?m)^\s+[A-Za-z0-9_-]+:\s*write\s*$")
        self.assertNotIn("${{ secrets.", WORKFLOW)
        self.assertIn("    timeout-minutes: 5", WORKFLOW)
        self.assertIn("  cancel-in-progress: true", WORKFLOW)
        self.assertIn("          persist-credentials: false", WORKFLOW)

        expression = "${{ github.event_name == 'pull_request' && github.event.pull_request.head.sha || github.sha }}"
        self.assertEqual(WORKFLOW.count(expression), 2)
        self.assertIn('          test "$(git rev-parse HEAD)" = "$EXPECTED_SHA"', WORKFLOW)

    def test_workflow_uses_only_immutable_checkout_action(self):
        refs = re.findall(r"(?m)^\s*(?:-\s*)?uses:\s*([^@\s]+)@([^\s#]+)", WORKFLOW)
        self.assertEqual([action for action, _ in refs], ["actions/checkout"])
        self.assertEqual(
            refs[0][1],
            "3d3c42e5aac5ba805825da76410c181273ba90b1",
        )

    def test_workflow_triggers_cover_tool_tests_and_contract(self):
        required = (
            '"tools/prepare-physical-share-bundle.py"',
            '"tests/test_physical_share_bundle.py"',
            '"tests/test_physical_share_bundle_workflow.py"',
            '".github/workflows/physical-share-bundle-quality.yml"',
        )
        for path in required:
            with self.subTest(path=path):
                self.assertEqual(WORKFLOW.count(path), 2)
        self.assertIn("  workflow_dispatch: {}", WORKFLOW)

    def test_workflow_pins_runtime_and_runs_only_focused_regressions(self):
        runtime = (
            '          python3 -c \'import platform, sys; '
            'assert platform.python_implementation() == "CPython"; '
            'assert sys.version_info[:2] == (3, 14), sys.version\''
        )
        self.assertEqual(WORKFLOW.count(runtime), 1)
        self.assertEqual(
            WORKFLOW.count("          python3 -m unittest tests.test_physical_share_bundle"),
            1,
        )

    def test_each_run_step_is_strict_bash_and_finishes_clean(self):
        lines = WORKFLOW.splitlines()
        run_indices = [index for index, line in enumerate(lines) if line == "        run: |"]
        step_indices = [index for index, line in enumerate(lines) if line.startswith("      - name:")]
        self.assertGreater(len(run_indices), 0)
        for run_index in run_indices:
            step_start = max(index for index in step_indices if index < run_index)
            later = [index for index in step_indices if index > step_start]
            step_end = min(later) if later else len(lines)
            step = lines[step_start:step_end]
            self.assertIn("        shell: bash", step)
            self.assertEqual(lines[run_index + 1], "          set -euo pipefail")

        self.assertIn("          git diff --exit-code -- .", WORKFLOW)
        self.assertIn("          git diff --cached --exit-code -- .", WORKFLOW)
        self.assertIn(
            '          test -z "$(git ls-files --others --exclude-standard)"',
            WORKFLOW,
        )


if __name__ == "__main__":
    unittest.main()
