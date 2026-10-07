import pathlib
import re
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "frozen-acceptance-tooling-test.yml"
CHECKOUT_SHA = "3d3c42e5aac5ba805825da76410c181273ba90b1"


class FrozenAcceptanceToolingWorkflowContractTests(unittest.TestCase):
    def setUp(self):
        self.text = WORKFLOW.read_text(encoding="utf-8")

    def test_uses_pinned_node24_checkout_only(self):
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
        self.assertIn("persist-credentials: false", self.text)
        self.assertNotIn("pull_request_target:", self.text)

    def test_hosted_runtime_is_reproducible(self):
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

    def test_permissions_are_read_only(self):
        self.assertRegex(
            self.text,
            r"(?ms)^permissions:\n  contents: read\n\nconcurrency:",
        )
        self.assertNotRegex(self.text, r"(?m)^    permissions:")

    def test_exact_head_checkout_remains_bound(self):
        expression = (
            "${{ github.event_name == 'pull_request' && "
            "github.event.pull_request.head.sha || github.sha }}"
        )
        self.assertIn(f"          ref: {expression}", self.text)
        self.assertIn(
            '          expected="${{ github.event_name == \'pull_request\' && github.event.pull_request.head.sha || github.sha }}"',
            self.text,
        )
        self.assertIn('          test "$revision" = "$expected"', self.text)

    def test_contract_test_is_triggered_and_executed(self):
        path = '      - "tests/test_frozen_acceptance_tooling_workflow.py"'
        self.assertEqual(
            self.text.count(path),
            2,
            "contract test must trigger both push and pull_request validation",
        )
        command = (
            "          python3 -m unittest discover -s tests "
            "-p 'test_frozen_acceptance_tooling_workflow.py'"
        )
        self.assertEqual(self.text.count(command), 1)

    def test_all_run_steps_fail_closed_under_bash(self):
        lines = self.text.splitlines()
        run_indices = [
            index for index, line in enumerate(lines)
            if line == "        run: |"
        ]
        self.assertTrue(run_indices)
        for index in run_indices:
            with self.subTest(run_line=index + 1):
                self.assertEqual(lines[index + 1], "          set -euo pipefail")
        self.assertNotIn("continue-on-error: true", self.text)


if __name__ == "__main__":
    unittest.main()
