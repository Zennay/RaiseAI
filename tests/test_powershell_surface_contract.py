import os
import pathlib
import re
import subprocess
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "powershell-surface-contract.yml"
EXPECTED_CRITICAL = {
    "install-watch-windows.ps1",
}


def tracked_powershell_paths():
    raw = subprocess.check_output(["git", "ls-files", "-z"], cwd=ROOT)
    return sorted(
        item
        for item in raw.decode("utf-8").split("\0")
        if item and pathlib.PurePosixPath(item).suffix.lower() == ".ps1"
    )


def parse_powershell(path):
    script = (
        '$tokens = $null; $errors = $null; '
        '[void][System.Management.Automation.Language.Parser]::ParseFile('
        '$env:RAISE_PS_FILE, [ref]$tokens, [ref]$errors); '
        'if ($errors.Count -ne 0) { '
        '$errors | ForEach-Object { [Console]::Error.WriteLine($_.Message) }; exit 1 }'
    )
    return subprocess.run(
        ["pwsh", "-NoLogo", "-NoProfile", "-NonInteractive", "-Command", script],
        cwd=ROOT,
        env={**os.environ, "RAISE_PS_FILE": str(path)},
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )


class PowerShellSurfaceContractTests(unittest.TestCase):
    def setUp(self):
        self.workflow = WORKFLOW.read_text(encoding="utf-8")

    def test_tracked_powershell_surface_is_nonempty_and_includes_critical_entrypoint(self):
        paths = tracked_powershell_paths()
        self.assertTrue(paths, "tracked PowerShell discovery must find files")
        self.assertTrue(
            EXPECTED_CRITICAL.issubset(paths),
            f"critical PowerShell files missing from discovery: {sorted(EXPECTED_CRITICAL - set(paths))}",
        )

    def test_every_tracked_powershell_file_is_regular_utf8_and_syntax_valid(self):
        for relative in tracked_powershell_paths():
            with self.subTest(path=relative):
                path = ROOT / relative
                self.assertFalse(
                    path.is_symlink(),
                    f"{relative} must be a regular repository file, not a symlink",
                )
                self.assertTrue(path.is_file(), f"{relative} must resolve to a regular file")
                path.read_bytes().decode("utf-8")
                parsed = parse_powershell(path)
                self.assertEqual(
                    parsed.returncode,
                    0,
                    f"{relative} must parse as PowerShell: {parsed.stderr}",
                )

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

    def test_workflow_triggers_cover_current_and_future_powershell_surfaces(self):
        expected = [
            "*.ps1",
            "**/*.ps1",
            "tests/test_powershell_surface_contract.py",
            ".github/workflows/powershell-surface-contract.yml",
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

    def test_workflow_pins_exact_powershell_runtime(self):
        command = (
            'test "$(pwsh -NoLogo -NoProfile -NonInteractive -Command '
            "'$PSVersionTable.PSVersion.ToString()')\" = \"7.6.6\""
        )
        self.assertEqual(
            self.workflow.count(command),
            1,
            "PowerShell parser runtime must remain pinned to reviewed 7.6.6",
        )
        self.assertNotIn(
            "pwsh -NoLogo -NoProfile -NonInteractive -Command "
            "'$PSVersionTable.PSVersion.ToString()'\n",
            self.workflow,
            "runtime probe must fail closed instead of only printing the version",
        )

    def test_workflow_pins_exact_python_runtime(self):
        assertion = (
            'python3 -c \'import platform, sys; '
            'assert platform.python_implementation() == "CPython"; '
            'assert sys.version_info[:2] == (3, 12), sys.version\''
        )
        self.assertEqual(
            self.workflow.count(assertion),
            1,
            "hosted Python harness must remain pinned to CPython 3.12",
        )

    def test_workflow_execution_surface_is_exact(self):
        lines = self.workflow.splitlines()
        top_level = [
            match.group(1)
            for line in lines
            if (match := re.fullmatch(r"([A-Za-z0-9_-]+):.*", line))
        ]
        self.assertEqual(top_level, ["name", "on", "permissions", "concurrency", "jobs"])

        on_start = lines.index("on:") + 1
        permissions_start = lines.index("permissions:")
        events = [
            match.group(1)
            for line in lines[on_start:permissions_start]
            if (match := re.fullmatch(r"  ([A-Za-z0-9_-]+):", line))
        ]
        self.assertEqual(events, ["push", "pull_request"])

        def event_block(event):
            start = lines.index(f"  {event}:") + 1
            block = []
            for line in lines[start:]:
                if line and not line.startswith("    "):
                    break
                block.append(line)
            return block

        push = event_block("push")
        push_keys = [
            match.group(1)
            for line in push
            if (match := re.fullmatch(r"    ([A-Za-z0-9_-]+):", line))
        ]
        self.assertEqual(push_keys, ["branches", "paths"])
        self.assertEqual(push[push.index("    branches:") + 1], "      - main")

        pull_request = event_block("pull_request")
        pr_keys = [
            match.group(1)
            for line in pull_request
            if (match := re.fullmatch(r"    ([A-Za-z0-9_-]+):", line))
        ]
        self.assertEqual(pr_keys, ["paths"])

        concurrency_start = lines.index("concurrency:") + 1
        jobs_start = lines.index("jobs:")
        concurrency_keys = [
            match.group(1)
            for line in lines[concurrency_start:jobs_start]
            if (match := re.fullmatch(r"  ([A-Za-z0-9_-]+):.*", line))
        ]
        self.assertEqual(concurrency_keys, ["group", "cancel-in-progress"])

        jobs_block = self.workflow.split("\njobs:\n", 1)[1]
        job_keys = [
            match.group(1)
            for line in jobs_block.splitlines()[1:]
            if (match := re.fullmatch(r"    ([A-Za-z0-9_-]+):.*", line))
        ]
        self.assertEqual(job_keys, ["runs-on", "timeout-minutes", "env", "steps"])

        env_start = lines.index("    env:") + 1
        expected_env = [
            "      LANG: C.UTF-8",
            "      LC_ALL: C.UTF-8",
            '      PYTHONHASHSEED: "1"',
            '      PYTHONNOUSERSITE: "1"',
            '      PYTHONDONTWRITEBYTECODE: "1"',
            "      TZ: UTC",
        ]
        self.assertEqual(lines[env_start : env_start + len(expected_env)], expected_env)

        step_starts = [index for index, line in enumerate(lines) if line.startswith("      - name:")]
        expected_names = [
            "Checkout exact tested revision",
            "Verify exact tested revision",
            "Verify PowerShell runtime",
            "Verify Python runtime",
            "Validate tracked PowerShell surface",
            "Run PowerShell surface regression contract",
            "Verify worktree remains clean",
        ]
        names = [lines[index].removeprefix("      - name: ") for index in step_starts]
        self.assertEqual(names, expected_names)

        expected_keys = {
            "Checkout exact tested revision": ["name", "uses", "with"],
            "Verify exact tested revision": ["name", "shell", "env", "run"],
            "Verify PowerShell runtime": ["name", "shell", "run"],
            "Verify Python runtime": ["name", "shell", "run"],
            "Validate tracked PowerShell surface": ["name", "shell", "run"],
            "Run PowerShell surface regression contract": ["name", "shell", "run"],
            "Verify worktree remains clean": ["name", "shell", "run"],
        }
        for position, start in enumerate(step_starts):
            end = step_starts[position + 1] if position + 1 < len(step_starts) else len(lines)
            step = lines[start:end]
            name = names[position]
            keys = ["name"]
            for line in step[1:]:
                match = re.fullmatch(r"        ([A-Za-z0-9_-]+):.*", line)
                if match:
                    keys.append(match.group(1))
            self.assertEqual(keys, expected_keys[name])

        def step_named(name):
            start = lines.index(f"      - name: {name}")
            following = [
                index for index, line in enumerate(lines)
                if index > start and line.startswith("      - name:")
            ]
            end = min(following) if following else len(lines)
            return lines[start:end]

        checkout = step_named("Checkout exact tested revision")
        with_start = checkout.index("        with:") + 1
        checkout_keys = []
        for line in checkout[with_start:]:
            match = re.fullmatch(r"          ([A-Za-z0-9_-]+):.*", line)
            if match:
                checkout_keys.append(match.group(1))
                continue
            break
        self.assertEqual(checkout_keys, ["ref", "persist-credentials"])

        verifier = step_named("Verify exact tested revision")
        verifier_env_start = verifier.index("        env:") + 1
        verifier_keys = []
        for line in verifier[verifier_env_start:]:
            match = re.fullmatch(r"          ([A-Za-z0-9_-]+):.*", line)
            if match:
                verifier_keys.append(match.group(1))
                continue
            break
        self.assertEqual(verifier_keys, ["EXPECTED_SHA"])

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

    def test_workflow_runs_dynamic_powershell_validation_and_regression(self):
        for token in (
            'subprocess.check_output(["git", "ls-files", "-z"])',
            'pathlib.PurePosixPath(item).suffix.lower() == ".ps1"',
            "candidate.is_symlink()",
            "tracked PowerShell files must not be symlinks",
            "System.Management.Automation.Language.Parser",
            "python3 -m unittest tests.test_powershell_surface_contract",
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
