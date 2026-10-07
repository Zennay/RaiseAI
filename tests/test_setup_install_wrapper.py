import os
import shutil
import subprocess
import tempfile
import textwrap
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class SetupInstallWrapperTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.repo = self.root / "repo"
        self.repo.mkdir()
        self.outside = self.root / "outside"
        self.outside.mkdir()
        self.trace = self.root / "upgrade-trace"

        self.wrapper = self.repo / "setup-and-install-watch.command"
        shutil.copy2(ROOT / "setup-and-install-watch.command", self.wrapper)
        self.wrapper.chmod(0o755)

    def tearDown(self):
        self.temp.cleanup()

    def write_upgrade(self, body):
        upgrade = self.repo / "upgrade-watch.command"
        upgrade.write_text(
            "#!/bin/bash\nset -euo pipefail\n" + textwrap.dedent(body),
            encoding="utf-8",
        )
        upgrade.chmod(0o755)

    def run_wrapper(self, *args):
        env = os.environ.copy()
        env["TRACE_FILE"] = str(self.trace)
        return subprocess.run(
            [str(self.wrapper), *args],
            cwd=self.outside,
            env=env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )

    def test_delegates_to_sibling_from_repository_directory_and_preserves_exit(self):
        self.write_upgrade(
            """
            printf '%s\n' "$PWD" > "$TRACE_FILE"
            exit 23
            """
        )

        result = self.run_wrapper()

        self.assertEqual(result.returncode, 23, result.stdout)
        self.assertEqual(
            self.trace.read_text(encoding="utf-8").strip(),
            str(self.repo),
        )
        self.assertIn("Raise AI first-time setup/install", result.stdout)
        self.assertNotIn("Race AI", result.stdout)

    def test_rejects_unexpected_arguments_before_upgrade(self):
        self.write_upgrade(
            """
            printf 'invoked\n' > "$TRACE_FILE"
            exit 0
            """
        )

        result = self.run_wrapper("unexpected")

        self.assertEqual(result.returncode, 2, result.stdout)
        self.assertIn("Usage: ./setup-and-install-watch.command", result.stdout)
        self.assertFalse(self.trace.exists())


class SetupWrapperWorkflowContractTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.workflow = (
            ROOT / ".github" / "workflows" / "setup-wrapper-quality.yml"
        ).read_text(encoding="utf-8")

    def test_workflow_is_self_hosted_read_only_and_immutably_pinned(self):
        self.assertIn(
            "    runs-on: [self-hosted, linux, x64, vps-bb300bba]",
            self.workflow,
        )
        self.assertNotIn("ubuntu-latest", self.workflow)
        self.assertIn("permissions:\n  contents: read", self.workflow)
        self.assertEqual(self.workflow.count("        uses:"), 1)
        self.assertIn(
            "uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1",
            self.workflow,
        )
        self.assertIn("          persist-credentials: false", self.workflow)
        self.assertIn("    timeout-minutes: 5", self.workflow)
        self.assertNotIn("continue-on-error: true", self.workflow)
        self.assertNotIn("secrets.", self.workflow)

    def test_workflow_trigger_surface_covers_every_contract_input(self):
        for path in (
            "setup-and-install-watch.command",
            "tests/test_setup_install_wrapper.py",
            ".github/workflows/setup-wrapper-quality.yml",
        ):
            with self.subTest(path=path):
                self.assertEqual(
                    self.workflow.count(f'      - "{path}"'),
                    2,
                    f"{path} must trigger both push and pull_request validation",
                )
        self.assertIn(
            "  push:\n    branches:\n      - main\n    paths:",
            self.workflow,
        )
        self.assertIn("  pull_request:\n    paths:", self.workflow)

    def test_workflow_binds_execution_to_exact_head_and_expected_runner(self):
        self.assertIn(
            "EXPECTED_SHA: ${{ github.event_name == 'pull_request' && "
            "github.event.pull_request.head.sha || github.sha }}",
            self.workflow,
        )
        self.assertIn(
            '          test "$(hostname)" = "vps-bb300bba"',
            self.workflow,
        )
        self.assertIn(
            '          test "$(git rev-parse HEAD)" = "$EXPECTED_SHA"',
            self.workflow,
        )
        self.assertIn(
            '          test -z "$(git status --porcelain --untracked-files=normal)"',
            self.workflow,
        )
        self.assertEqual(self.workflow.count("          set -euo pipefail"), 2)


if __name__ == "__main__":
    unittest.main()
