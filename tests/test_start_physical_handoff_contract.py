import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class PhysicalHandoffLauncherContractTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.launcher = self.root / "start-physical-handoff.command"
        shutil.copy2(ROOT / "start-physical-handoff.command", self.launcher)
        self.launcher.chmod(0o755)

    def tearDown(self):
        self.temp.cleanup()

    def run_launcher(self, *args):
        return subprocess.run(
            ["bash", str(self.launcher), *args],
            cwd=self.root,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )

    def prepare_minimal_handoff(self, identity_text):
        (self.root / "RaiseAI-v1.5.2-debug.apk").write_bytes(b"apk")
        (self.root / "RaiseAI-v1.5.2-source.bundle").write_bytes(b"bundle")
        (self.root / "BUILD-IDENTITY.txt").write_text(identity_text, encoding="utf-8")

    def test_requires_exactly_one_argument(self):
        no_args = self.run_launcher()
        self.assertEqual(no_args.returncode, 2, no_args.stdout)
        self.assertIn("Usage: bash ./start-physical-handoff.command", no_args.stdout)

        extra_args = self.run_launcher("--verify-only", "unexpected")
        self.assertEqual(extra_args.returncode, 2, extra_args.stdout)
        self.assertIn("Usage: bash ./start-physical-handoff.command", extra_args.stdout)

    def test_rejects_unknown_option_before_artifact_access(self):
        result = self.run_launcher("--unexpected")
        self.assertEqual(result.returncode, 2, result.stdout)
        self.assertIn("Usage: bash ./start-physical-handoff.command", result.stdout)
        self.assertNotIn("Physical handoff must contain", result.stdout)

    def test_rejects_duplicate_source_revision_identity(self):
        self.prepare_minimal_handoff(
            "source_revision=" + "1" * 40 + "\n"
            "source_revision=" + "2" * 40 + "\n"
            "apk_sha256=" + "a" * 64 + "\n"
            "source_bundle_sha256=" + "b" * 64 + "\n"
        )
        result = self.run_launcher("--verify-only")
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn(
            "BUILD-IDENTITY.txt must contain exactly one source_revision entry.",
            result.stdout,
        )

    def test_rejects_duplicate_apk_digest_identity(self):
        self.prepare_minimal_handoff(
            "source_revision=" + "1" * 40 + "\n"
            "apk_sha256=" + "a" * 64 + "\n"
            "apk_sha256=" + "c" * 64 + "\n"
            "source_bundle_sha256=" + "b" * 64 + "\n"
        )
        result = self.run_launcher("--verify-only")
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn(
            "BUILD-IDENTITY.txt must contain exactly one apk_sha256 entry.",
            result.stdout,
        )

    def test_rejects_missing_bundle_digest_identity(self):
        self.prepare_minimal_handoff(
            "source_revision=" + "1" * 40 + "\n"
            "apk_sha256=" + "a" * 64 + "\n"
        )
        result = self.run_launcher("--verify-only")
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn(
            "BUILD-IDENTITY.txt must contain exactly one source_bundle_sha256 entry.",
            result.stdout,
        )


class PhysicalHandoffLauncherWorkflowContractTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.workflow = (
            ROOT / ".github" / "workflows" / "physical-handoff-launcher-quality.yml"
        ).read_text(encoding="utf-8")

    def test_workflow_is_self_hosted_read_only_and_pinned(self):
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

    def test_workflow_trigger_surface_is_symmetric(self):
        for path in (
            "start-physical-handoff.command",
            "tests/test_start_physical_handoff_contract.py",
            ".github/workflows/physical-handoff-launcher-quality.yml",
        ):
            with self.subTest(path=path):
                self.assertEqual(self.workflow.count(f'      - "{path}"'), 2)
        self.assertIn(
            "  push:\n    branches:\n      - main\n    paths:",
            self.workflow,
        )
        self.assertIn("  pull_request:\n    paths:", self.workflow)

    def test_workflow_binds_exact_head_runner_and_clean_tree(self):
        self.assertIn(
            "EXPECTED_SHA: ${{ github.event_name == 'pull_request' && github.event.pull_request.head.sha || github.sha }}",
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
        self.assertGreaterEqual(
            self.workflow.count(
                'test -z "$(git status --porcelain --untracked-files=normal)"'
            ),
            2,
        )
        self.assertEqual(self.workflow.count("          set -euo pipefail"), 2)


if __name__ == "__main__":
    unittest.main()
