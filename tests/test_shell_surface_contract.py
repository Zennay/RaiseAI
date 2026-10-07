import pathlib
import re
import subprocess
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "shell-surface-contract.yml"
EXPECTED_CRITICAL = {
    "gradlew",
    "start-frozen-acceptance.command",
    "start-physical-handoff.command",
    "gateway/deploy/install-user-gateway.sh",
    "gateway/deploy/assert-idempotent-redeploy.sh",
}
ALLOWED_SHEBANGS = {"#!/bin/bash", "#!/usr/bin/env bash"}


def tracked_shell_paths():
    raw = subprocess.check_output(
        ["git", "ls-files", "-z"],
        cwd=ROOT,
    )
    paths = []
    for item in raw.decode("utf-8").split("\0"):
        if not item:
            continue
        path = pathlib.PurePosixPath(item)
        if item == "gradlew" or path.suffix in {".command", ".sh"}:
            paths.append(item)
    return sorted(paths)


class ShellSurfaceContractTests(unittest.TestCase):
    def setUp(self):
        self.workflow = WORKFLOW.read_text(encoding="utf-8")

    def test_tracked_shell_surface_is_nonempty_and_includes_critical_entrypoints(self):
        paths = tracked_shell_paths()
        self.assertTrue(paths, "tracked shell discovery must find entrypoints")
        self.assertTrue(
            EXPECTED_CRITICAL.issubset(paths),
            f"critical shell entrypoints missing from discovery: {sorted(EXPECTED_CRITICAL - set(paths))}",
        )

    def test_every_tracked_shell_entrypoint_is_strict_bash_and_syntax_valid(self):
        for relative in tracked_shell_paths():
            with self.subTest(path=relative):
                path = ROOT / relative
                lines = path.read_text(encoding="utf-8").splitlines()
                self.assertGreaterEqual(len(lines), 2, f"{relative} must include shebang + strict mode")
                self.assertIn(lines[0], ALLOWED_SHEBANGS, f"{relative} must declare Bash explicitly")
                self.assertEqual(
                    lines[1],
                    "set -euo pipefail",
                    f"{relative} must fail closed before executing commands",
                )
                completed = subprocess.run(
                    ["bash", "-n", str(path)],
                    cwd=ROOT,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    check=False,
                )
                self.assertEqual(
                    completed.returncode,
                    0,
                    f"{relative} must pass bash -n: {completed.stderr}",
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

    def test_workflow_triggers_cover_current_and_future_shell_surfaces(self):
        expected = [
            "*.command",
            "**/*.command",
            "*.sh",
            "**/*.sh",
            "gradlew",
            "tests/test_shell_surface_contract.py",
            ".github/workflows/shell-surface-contract.yml",
        ]
        for event in ("push", "pull_request"):
            with self.subTest(event=event):
                self.assertEqual(self._trigger_paths(event), expected)

    def test_workflow_is_hosted_read_only_exact_head_and_bounded(self):
        self.assertIn("runs-on: ubuntu-24.04", self.workflow)
        self.assertNotIn("self-hosted", self.workflow)
        self.assertIn("permissions:\n  contents: read\n", self.workflow)
        self.assertNotRegex(self.workflow, r"\$\{\{\s*secrets\.")
        self.assertIn("timeout-minutes: 5", self.workflow)
        self.assertIn("cancel-in-progress: true", self.workflow)
        expression = (
            "${{ github.event_name == 'pull_request' && "
            "github.event.pull_request.head.sha || github.sha }}"
        )
        self.assertEqual(self.workflow.count(expression), 2)
        self.assertIn("persist-credentials: false", self.workflow)

    def test_workflow_uses_only_immutable_checkout_action(self):
        refs = re.findall(
            r"^\s*(?:-\s*)?uses:\s*([^@\s]+)@([^\s#]+)",
            self.workflow,
            flags=re.MULTILINE,
        )
        self.assertEqual([action for action, _ in refs], ["actions/checkout"])
        self.assertRegex(refs[0][1], r"^[0-9a-f]{40}$")

    def test_workflow_runs_dynamic_shell_discovery_and_contract(self):
        for token in (
            'git ls-files -z',
            "path.suffix in {\".command\", \".sh\"}",
            'subprocess.run(["bash", "-n", path], check=True)',
            "python3 -m unittest tests.test_shell_surface_contract",
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
        self.assertNotIn("continue-on-error: true", self.workflow)


if __name__ == "__main__":
    unittest.main()
