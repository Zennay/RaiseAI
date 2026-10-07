import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LAUNCHER = ROOT / "open-in-android-studio.command"


class AndroidStudioLauncherContractTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = LAUNCHER.read_text(encoding="utf-8")

    def run_launcher(self, *args):
        return subprocess.run(
            [str(LAUNCHER), *args],
            cwd=ROOT,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=5,
        )

    def test_shell_contract_is_strict_and_repository_relative(self):
        lines = self.source.splitlines()
        self.assertEqual(lines[0], "#!/bin/bash")
        self.assertEqual(lines[1], "set -euo pipefail")
        self.assertIn('SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd -P)"', self.source)
        self.assertIn('cd "$SCRIPT_DIR"', self.source)

    def test_unexpected_arguments_fail_closed_before_launch(self):
        result = self.run_launcher("unexpected")
        self.assertEqual(result.returncode, 2, result.stdout)
        self.assertIn("Usage: ./open-in-android-studio.command", result.stdout)

    def test_missing_android_studio_is_nonzero_and_noninteractive_safe(self):
        if Path("/Applications/Android Studio.app").is_dir():
            self.skipTest("Android Studio exists on this runner")
        result = self.run_launcher()
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("Android Studio was not found", result.stdout)

    def test_success_path_launches_exact_bundle_and_propagates_open_exit_status(self):
        self.assertEqual(
            self.source.count('ANDROID_STUDIO_APP="/Applications/Android Studio.app"'),
            1,
        )
        self.assertIn('if [ -d "$ANDROID_STUDIO_APP" ]; then', self.source)
        self.assertIn(
            'exec open -a "$ANDROID_STUDIO_APP" "$SCRIPT_DIR"',
            self.source,
        )
        self.assertNotIn('exec open -a "Android Studio"', self.source)
        self.assertNotIn('open -a "$ANDROID_STUDIO_APP" "$PWD"', self.source)


class AndroidStudioLauncherWorkflowContractTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.workflow = (
            ROOT / ".github" / "workflows" / "android-studio-launcher-quality.yml"
        ).read_text(encoding="utf-8")

    def test_workflow_is_exact_head_read_only_and_immutable(self):
        self.assertIn(
            "    runs-on: [self-hosted, linux, x64, vps-bb300bba]",
            self.workflow,
        )
        self.assertIn("permissions:\n  contents: read", self.workflow)
        self.assertEqual(self.workflow.count("        uses:"), 1)
        self.assertIn(
            "uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1",
            self.workflow,
        )
        exact_head = "${{ github.event_name == 'pull_request' && github.event.pull_request.head.sha || github.sha }}"
        self.assertEqual(self.workflow.count(f"          ref: {exact_head}"), 1)
        self.assertEqual(self.workflow.count(f"          EXPECTED_SHA: {exact_head}"), 1)
        self.assertIn("          persist-credentials: false", self.workflow)
        self.assertIn(
            '          test "$(git rev-parse HEAD)" = "$EXPECTED_SHA"',
            self.workflow,
        )
        self.assertIn(
            '          test "$(hostname)" = "vps-bb300bba"',
            self.workflow,
        )
        self.assertNotIn("pull_request_target:", self.workflow)
        self.assertNotIn("contents: write", self.workflow)
        self.assertNotIn("id-token: write", self.workflow)
        self.assertNotIn("actions: write", self.workflow)
        self.assertNotIn("secrets.", self.workflow)
        self.assertNotIn("continue-on-error: true", self.workflow)
        for command in (
            "          git diff --exit-code -- .",
            "          git diff --cached --exit-code -- .",
            '          test -z "$(git ls-files --others --exclude-standard)"',
        ):
            with self.subTest(clean_worktree_command=command):
                self.assertIn(command, self.workflow)

    def test_workflow_trigger_surface_covers_all_contract_inputs(self):
        for path in (
            "open-in-android-studio.command",
            "tests/test_android_studio_launcher.py",
            ".github/workflows/android-studio-launcher-quality.yml",
        ):
            with self.subTest(path=path):
                self.assertEqual(
                    self.workflow.count(f'      - "{path}"'),
                    2,
                    f"{path} must trigger both push and pull_request validation",
                )
        self.assertIn("  pull_request:\n    paths:", self.workflow)
        self.assertIn(
            "  push:\n    branches:\n      - main\n    paths:",
            self.workflow,
        )


if __name__ == "__main__":
    unittest.main()
