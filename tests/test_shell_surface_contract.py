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


def decode_shell_source(raw: bytes, *, relative: str) -> str:
    if b"\r" in raw:
        raise ValueError(f"{relative} must use LF line endings without carriage returns")
    try:
        return raw.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise ValueError(f"{relative} must be strict UTF-8") from exc


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
                self.assertFalse(
                    path.is_symlink(),
                    f"{relative} must be a regular repository file, not a symlink",
                )
                text = decode_shell_source(path.read_bytes(), relative=relative)
                lines = text.splitlines()
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

    def test_shell_source_rejects_crlf_and_bare_carriage_returns(self):
        for payload in (
            b"#!/bin/bash\r\nset -euo pipefail\r\necho ok\r\n",
            b"#!/bin/bash\nset -euo pipefail\necho bad\rvalue\n",
        ):
            with self.subTest(payload=payload):
                with self.assertRaisesRegex(ValueError, "LF line endings"):
                    decode_shell_source(payload, relative="fixture.command")

    def test_shell_source_rejects_non_utf8_bytes(self):
        with self.assertRaisesRegex(ValueError, "strict UTF-8"):
            decode_shell_source(
                b"#!/bin/bash\nset -euo pipefail\necho \xff\n",
                relative="fixture.command",
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

    def test_workflow_pins_exact_bash_runtime(self):
        self.assertIn("- name: Verify Bash runtime", self.workflow)
        self.assertEqual(
            self.workflow.count('test "${BASH_VERSION}" = "5.2.21(1)-release"'),
            1,
            "shell syntax parser must remain pinned to reviewed Bash 5.2.21(1)-release",
        )

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
            'subprocess.check_output(["git", "ls-files", "-z"])',
            'path.suffix in {".command", ".sh"}',
            'candidate.is_symlink()',
            'tracked shell entrypoints must not be symlinks',
            'source = candidate.read_bytes()',
            'if b"\\r" in source:',
            'shell source must use LF line endings without carriage returns',
            'source.decode("utf-8", errors="strict")',
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


    def test_workflow_trigger_and_execution_surfaces_are_exact(self):
        lines = self.workflow.splitlines()

        top_level = []
        for line in lines:
            match = re.fullmatch(r"([A-Za-z0-9_-]+):.*", line)
            if match:
                top_level.append(match.group(1))
        self.assertEqual(
            top_level,
            ["name", "on", "permissions", "concurrency", "jobs"],
            "shell workflow must not gain unreviewed top-level controls",
        )

        on_start = lines.index("on:") + 1
        permissions_start = lines.index("permissions:")
        events = []
        for line in lines[on_start:permissions_start]:
            match = re.fullmatch(r"  ([A-Za-z0-9_-]+):", line)
            if match:
                events.append(match.group(1))
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
        branches_start = push.index("    branches:") + 1
        self.assertEqual(push[branches_start], "      - main")

        pull_request = event_block("pull_request")
        pr_keys = [
            match.group(1)
            for line in pull_request
            if (match := re.fullmatch(r"    ([A-Za-z0-9_-]+):", line))
        ]
        self.assertEqual(
            pr_keys,
            ["paths"],
            "pull_request must not gain type or branch filters that can skip synchronize validation",
        )

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
                "TZ",
            ],
        )

    def test_workflow_step_and_nested_mapping_surfaces_are_exact(self):
        lines = self.workflow.splitlines()
        step_starts = [
            index
            for index, line in enumerate(lines)
            if line.startswith("      - name:")
        ]
        expected_names = [
            "Checkout exact tested revision",
            "Verify exact tested revision",
            "Verify Bash runtime",
            "Verify Python runtime",
            "Validate tracked shell surface",
            "Run shell surface regression contract",
            "Verify worktree remains clean",
        ]
        self.assertEqual(
            [lines[index].removeprefix("      - name: ") for index in step_starts],
            expected_names,
            "shell workflow must not gain unreviewed steps",
        )

        expected_keys = {
            "Checkout exact tested revision": ["name", "uses", "with"],
            "Verify exact tested revision": ["name", "shell", "env", "run"],
            "Verify Bash runtime": ["name", "shell", "run"],
            "Verify Python runtime": ["name", "shell", "run"],
            "Validate tracked shell surface": ["name", "shell", "run"],
            "Run shell surface regression contract": ["name", "shell", "run"],
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
            self.assertEqual(keys, expected_keys[name])

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
        checkout_keys = []
        for line in checkout[with_start:]:
            match = re.fullmatch(r"          ([A-Za-z0-9_-]+):.*", line)
            if match:
                checkout_keys.append(match.group(1))
                continue
            break
        self.assertEqual(checkout_keys, ["ref", "persist-credentials"])

        verifier = step_named("Verify exact tested revision")
        env_start = verifier.index("        env:") + 1
        verifier_keys = []
        for line in verifier[env_start:]:
            match = re.fullmatch(r"          ([A-Za-z0-9_-]+):.*", line)
            if match:
                verifier_keys.append(match.group(1))
                continue
            break
        self.assertEqual(verifier_keys, ["EXPECTED_SHA"])


if __name__ == "__main__":
    unittest.main()
