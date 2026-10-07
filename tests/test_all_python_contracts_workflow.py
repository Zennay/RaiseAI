from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "all-python-contracts.yml"
CHECKOUT_SHA = "3d3c42e5aac5ba805825da76410c181273ba90b1"


class AllPythonContractsWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.text = WORKFLOW.read_text(encoding="utf-8")

    def test_runs_on_every_pull_request_and_main_push(self):
        self.assertRegex(
            self.text,
            r"(?ms)^on:\n  push:\n    branches:\n      - main\n  pull_request:\n",
        )
        self.assertNotIn("    paths:", self.text)
        self.assertNotIn("    paths-ignore:", self.text)
        self.assertNotIn("pull_request_target:", self.text)

    def test_is_hosted_read_only_and_secret_free(self):
        self.assertEqual(self.text.count("    runs-on: ubuntu-24.04"), 1)
        self.assertNotIn("ubuntu-latest", self.text)
        self.assertNotIn("self-hosted", self.text)
        self.assertRegex(
            self.text,
            r"(?ms)^permissions:\n  contents: read\n\nconcurrency:",
        )
        self.assertNotRegex(self.text, r"(?m)^    permissions:")
        self.assertNotRegex(self.text, r"\$\{\{\s*secrets\.")

    def test_checkout_is_immutable_exact_head_and_credential_free(self):
        refs = re.findall(
            r"^\s*(?:-\s*)?uses:\s*([^@\s]+)@([^\s#]+)",
            self.text,
            flags=re.MULTILINE,
        )
        self.assertEqual(refs, [("actions/checkout", CHECKOUT_SHA)])
        expression = (
            "${{ github.event_name == 'pull_request' && "
            "github.event.pull_request.head.sha || github.sha }}"
        )
        self.assertEqual(self.text.count(f"          ref: {expression}"), 1)
        self.assertEqual(self.text.count(f"          EXPECTED_SHA: {expression}"), 1)
        self.assertEqual(self.text.count("          persist-credentials: false"), 1)
        self.assertIn('          test "$(git rev-parse HEAD)" = "$EXPECTED_SHA"', self.text)

    def test_runtime_and_environment_are_reproducible(self):
        for line in (
            "      LANG: C.UTF-8",
            "      LC_ALL: C.UTF-8",
            '      PYTHONHASHSEED: "1"',
            '      PYTHONNOUSERSITE: "1"',
            '      PYTHONDONTWRITEBYTECODE: "1"',
            "      PYTHONPYCACHEPREFIX: /tmp/raise-all-contracts-pyc",
            "      TZ: UTC",
        ):
            with self.subTest(line=line):
                self.assertEqual(self.text.count(line), 1)

        runtime = (
            '          python3 -c \'import platform, sys; '
            'assert platform.python_implementation() == "CPython"; '
            'assert sys.version_info[:2] == (3, 12), sys.version\''
        )
        self.assertEqual(self.text.count(runtime), 1)

    def test_discovers_every_python_contract_through_zero_skip_runner(self):
        self.assertEqual(
            self.text.count("          python3 tools/run_python_contracts.py"),
            1,
        )
        self.assertNotRegex(
            self.text,
            r"python3 -m unittest(?:\s+discover|\s+tests\.)",
            "aggregate lane must use the zero-skip discovery runner",
        )

    def test_all_run_steps_are_strict_bash_and_worktree_is_clean(self):
        lines = self.text.splitlines()
        step_starts = [
            index for index, line in enumerate(lines)
            if line.startswith("      - name:")
        ]
        run_indices = [
            index for index, line in enumerate(lines)
            if line == "        run: |"
        ]
        self.assertEqual(len(run_indices), 4)
        for run_index in run_indices:
            with self.subTest(line=run_index + 1):
                step_start = max(i for i in step_starts if i < run_index)
                following = [i for i in step_starts if i > step_start]
                step_end = min(following) if following else len(lines)
                step = lines[step_start:step_end]
                self.assertIn("        shell: bash", step)
                self.assertEqual(lines[run_index + 1], "          set -euo pipefail")

        for command in (
            "          git diff --exit-code -- .",
            "          git diff --cached --exit-code -- .",
            '          test -z "$(git ls-files --others --exclude-standard)"',
        ):
            with self.subTest(command=command):
                self.assertEqual(self.text.count(command), 1)


if __name__ == "__main__":
    unittest.main()
