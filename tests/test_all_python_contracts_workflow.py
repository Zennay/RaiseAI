from pathlib import Path
import re
import stat
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "all-python-contracts.yml"
CHECKOUT_SHA = "3d3c42e5aac5ba805825da76410c181273ba90b1"


def read_workflow_text(path: Path) -> str:
    mode = path.lstat().st_mode
    if stat.S_ISLNK(mode):
        raise ValueError(f"{path.name}: workflow input must not be a symbolic link")
    if not stat.S_ISREG(mode):
        raise ValueError(f"{path.name}: workflow input must be a regular file")
    try:
        return path.read_bytes().decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise ValueError(f"{path.name}: workflow input must be valid UTF-8") from exc


class AllPythonContractsWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.text = read_workflow_text(WORKFLOW)

    def test_workflow_reader_rejects_symlink_nonregular_and_invalid_utf8(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            regular = root / "regular.yml"
            regular.write_text("on: [push]\n", encoding="utf-8")
            self.assertEqual(read_workflow_text(regular), "on: [push]\n")

            linked = root / "linked.yml"
            linked.symlink_to(regular)
            with self.assertRaisesRegex(ValueError, "must not be a symbolic link"):
                read_workflow_text(linked)

            directory = root / "directory.yml"
            directory.mkdir()
            with self.assertRaisesRegex(ValueError, "must be a regular file"):
                read_workflow_text(directory)

            invalid = root / "invalid.yml"
            invalid.write_bytes(b"on: [push]\n\xff")
            with self.assertRaisesRegex(ValueError, "must be valid UTF-8"):
                read_workflow_text(invalid)

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
            self.text.count("          python3 -I tools/run_python_contracts.py"),
            1,
        )
        self.assertNotIn(
            "          python3 tools/run_python_contracts.py",
            self.text,
            "aggregate contracts must ignore inherited Python environment/import paths",
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


    def test_trigger_and_concurrency_mappings_are_exact(self):
        lines = self.text.splitlines()
        on_start = lines.index("on:") + 1
        permissions_start = lines.index("permissions:")
        trigger_lines = lines[on_start:permissions_start]
        events = []
        for line in trigger_lines:
            match = re.fullmatch(r"  ([A-Za-z0-9_-]+):", line)
            if match:
                events.append(match.group(1))
        self.assertEqual(
            events,
            ["push", "pull_request"],
            "aggregate validation must retain only the audited trigger events",
        )

        push_start = lines.index("  push:") + 1
        push = []
        for line in lines[push_start:]:
            if line and not line.startswith("    "):
                break
            push.append(line)
        push_keys = []
        for line in push:
            match = re.fullmatch(r"    ([A-Za-z0-9_-]+):", line)
            if match:
                push_keys.append(match.group(1))
        self.assertEqual(push_keys, ["branches"])
        self.assertEqual(
            [line for line in push if line.startswith("      - ")],
            ["      - main"],
            "aggregate push validation must remain main-only",
        )

        pr_start = lines.index("  pull_request:") + 1
        pull_request = []
        for line in lines[pr_start:]:
            if line and not line.startswith("    "):
                break
            pull_request.append(line)
        self.assertEqual(
            [line for line in pull_request if line.strip()],
            [],
            "pull_request must stay unfiltered so synchronize commits always validate",
        )

        concurrency_start = lines.index("concurrency:") + 1
        jobs_start = lines.index("jobs:")
        concurrency = lines[concurrency_start:jobs_start]
        concurrency_keys = []
        for line in concurrency:
            match = re.fullmatch(r"  ([A-Za-z0-9_-]+):.*", line)
            if match:
                concurrency_keys.append(match.group(1))
        self.assertEqual(
            concurrency_keys,
            ["group", "cancel-in-progress"],
            "concurrency must not gain unreviewed controls",
        )

    def test_rejects_quoted_yaml_mapping_keys(self):
        quoted_mapping_key = re.compile(
            r'''(?m)^\s*(?:"[^"\n]+"|'[^'\n]+')\s*:'''
        )
        fixtures = (
            '        "continue-on-error": true',
            "        'working-directory': /tmp",
            '    "timeout-minutes": 30',
            "  'pull_request_target':",
        )
        for fixture in fixtures:
            with self.subTest(fixture=fixture):
                self.assertRegex(
                    fixture,
                    quoted_mapping_key,
                    "regression fixture must exercise the quoted-key detector",
                )

        self.assertNotRegex(
            self.text,
            quoted_mapping_key,
            "quoted YAML mapping keys can bypass aggregate workflow exact-surface parsers",
        )


    def test_checkout_and_revision_verifier_nested_mappings_are_exact(self):
        lines = self.text.splitlines()

        def step_named(name):
            start = lines.index(f"      - name: {name}")
            following = [
                index
                for index, line in enumerate(lines)
                if index > start and line.startswith("      - name:")
            ]
            end = min(following) if following else len(lines)
            return lines[start:end]

        checkout = step_named("Checkout exact tested revision")
        with_start = checkout.index("        with:") + 1
        with_keys = []
        for line in checkout[with_start:]:
            match = re.fullmatch(r"          ([A-Za-z0-9_-]+):.*", line)
            if match:
                with_keys.append(match.group(1))
                continue
            break
        self.assertEqual(
            with_keys,
            ["ref", "persist-credentials"],
            "checkout inputs must stay limited to exact-head binding and credential removal",
        )

        verifier = step_named("Verify exact tested revision")
        env_start = verifier.index("        env:") + 1
        verifier_env_keys = []
        for line in verifier[env_start:]:
            match = re.fullmatch(r"          ([A-Za-z0-9_-]+):.*", line)
            if match:
                verifier_env_keys.append(match.group(1))
                continue
            break
        self.assertEqual(
            verifier_env_keys,
            ["EXPECTED_SHA"],
            "revision verifier must not gain unreviewed environment controls",
        )


if __name__ == "__main__":
    unittest.main()
