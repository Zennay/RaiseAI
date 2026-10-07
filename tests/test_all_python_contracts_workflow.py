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
            r"python3 -m unittest(?:\\s+discover|\\s+tests\\.)",
            "aggregate lane must use the zero-skip discovery runner",
        )

    def test_execution_controls_are_fail_closed_and_bounded(self):
        self.assertNotRegex(
            self.text,
            r"(?m)^\s+if:\s*",
            "aggregate contract jobs and steps must not be conditionally skipped",
        )
        self.assertNotRegex(
            self.text,
            r"(?m)^\s+continue-on-error:\s*",
            "aggregate contract failures must fail the workflow",
        )
        self.assertEqual(
            self.text.count("    timeout-minutes: 10"),
            1,
            "aggregate contract job must keep a bounded runtime",
        )
        self.assertEqual(
            self.text.count(
                "  group: raise-all-python-contracts-${{ github.event.pull_request.number || github.ref }}"
            ),
            1,
        )
        self.assertEqual(
            self.text.count("  cancel-in-progress: true"),
            1,
            "superseded aggregate contract runs must be cancelled",
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


    def test_workflow_top_level_job_and_env_surfaces_are_exact(self):
        lines = self.text.splitlines()

        top_level = []
        for line in lines:
            match = re.fullmatch(r"([A-Za-z0-9_-]+):.*", line)
            if match:
                top_level.append(match.group(1))
        self.assertEqual(
            top_level,
            ["name", "on", "permissions", "concurrency", "jobs"],
            "aggregate workflow must not gain unreviewed top-level controls",
        )

        jobs_block = self.text.split("\njobs:\n", 1)[1]
        job_keys = []
        for line in jobs_block.splitlines()[1:]:
            match = re.fullmatch(r"    ([A-Za-z0-9_-]+):.*", line)
            if match:
                job_keys.append(match.group(1))
        self.assertEqual(
            job_keys,
            ["runs-on", "timeout-minutes", "env", "steps"],
            "aggregate contract job must keep an exact execution surface",
        )

        env_start = lines.index("    env:") + 1
        env_keys = []
        for line in lines[env_start:]:
            match = re.fullmatch(r"      ([A-Za-z0-9_-]+):.*", line)
            if match:
                env_keys.append(match.group(1))
                continue
            break
        self.assertEqual(
            env_keys,
            [
                "LANG",
                "LC_ALL",
                "PYTHONHASHSEED",
                "PYTHONNOUSERSITE",
                "PYTHONDONTWRITEBYTECODE",
                "PYTHONPYCACHEPREFIX",
                "TZ",
            ],
            "job environment must not gain unreviewed interpreter controls",
        )

    def test_step_mapping_surfaces_are_exact(self):
        lines = self.text.splitlines()
        step_starts = [
            index
            for index, line in enumerate(lines)
            if line.startswith("      - name:")
        ]
        expected_names = [
            "Checkout exact tested revision",
            "Verify exact tested revision",
            "Verify Python runtime",
            "Run every Python contract without skips",
            "Verify worktree remains clean",
        ]
        self.assertEqual(
            [lines[index].removeprefix("      - name: ") for index in step_starts],
            expected_names,
            "aggregate workflow must not gain unreviewed steps",
        )

        expected_keys = {
            "Checkout exact tested revision": ["name", "uses", "with"],
            "Verify exact tested revision": ["name", "shell", "env", "run"],
            "Verify Python runtime": ["name", "shell", "run"],
            "Run every Python contract without skips": ["name", "shell", "run"],
            "Verify worktree remains clean": ["name", "shell", "run"],
        }
        for position, start in enumerate(step_starts):
            end = step_starts[position + 1] if position + 1 < len(step_starts) else len(lines)
            step = lines[start:end]
            name = lines[start].removeprefix("      - name: ")
            keys = ["name"]
            for line in step[1:]:
                match = re.fullmatch(r"        ([A-Za-z0-9_-]+):.*", line)
                if match:
                    keys.append(match.group(1))
            self.assertEqual(
                keys,
                expected_keys[name],
                f"{name} must not gain unreviewed step-level controls",
            )


if __name__ == "__main__":
    unittest.main()
