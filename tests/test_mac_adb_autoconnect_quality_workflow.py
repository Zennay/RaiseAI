import pathlib
import re
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "mac-adb-autoconnect-quality.yml"


class MacAdbAutoconnectQualityWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.text = WORKFLOW.read_text(encoding="utf-8")

    def test_runner_and_timeout_are_exact(self):
        self.assertIn("runs-on: [self-hosted, vps-bb300bba]", self.text)
        self.assertIn("timeout-minutes: 5", self.text)
        self.assertNotIn("ubuntu-latest", self.text)

    def test_required_gate_is_not_prestart_cancelled(self):
        self.assertIn("concurrency:", self.text)
        self.assertIn("  cancel-in-progress: false", self.text)

    def test_permissions_are_read_only_and_secret_free(self):
        self.assertRegex(self.text, r"(?ms)^permissions:\n  contents: read\n")
        self.assertNotRegex(self.text, r"\$\{\{\s*secrets\.")

    def test_checkout_is_immutable_and_exact_head(self):
        self.assertIn(
            "uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1",
            self.text,
        )
        expression = (
            "${{ github.event_name == 'pull_request' && "
            "github.event.pull_request.head.sha || github.sha }}"
        )
        self.assertIn(f"ref: {expression}", self.text)
        self.assertIn(f"EXPECTED_SHA: {expression}", self.text)
        self.assertIn("persist-credentials: false", self.text)

    def test_all_run_steps_are_explicit_bash_and_strict(self):
        lines = self.text.splitlines()
        run_indices = [i for i, line in enumerate(lines) if line == "        run: |"]
        self.assertTrue(run_indices)
        step_starts = [
            i for i, line in enumerate(lines) if line.startswith("      - name:")
        ]
        for run_index in run_indices:
            with self.subTest(line=run_index + 1):
                start = max(i for i in step_starts if i < run_index)
                following = [i for i in step_starts if i > start]
                end = min(following) if following else len(lines)
                step = lines[start:end]
                self.assertIn("        shell: bash", step)
                self.assertEqual(lines[run_index + 1], "          set -euo pipefail")

    def test_trigger_paths_cover_contract_and_workflow(self):
        for required in (
            '"install-mac-adb-autoconnect.command"',
            '"tests/test_mac_adb_autoconnect_contract.py"',
            '"tests/test_mac_adb_autoconnect_quality_workflow.py"',
            '".github/workflows/mac-adb-autoconnect-quality.yml"',
        ):
            self.assertEqual(
                self.text.count(required),
                2,
                f"{required} must be present for push and pull_request",
            )

    def test_runner_identity_and_clean_worktree_are_enforced(self):
        self.assertIn('test "$RUNNER_NAME" = "vps-bb300bba"', self.text)
        self.assertIn('test "$(git rev-parse HEAD)" = "$EXPECTED_SHA"', self.text)
        self.assertIn("git diff --exit-code -- .", self.text)
        self.assertIn("git diff --cached --exit-code -- .", self.text)
        self.assertIn('test -z "$(git ls-files --others --exclude-standard)"', self.text)

    def test_external_action_surface_is_checkout_only(self):
        refs = re.findall(
            r"^\s*(?:-\s*)?uses:\s*([^@\s]+)@([^\s#]+)",
            self.text,
            flags=re.MULTILINE,
        )
        self.assertEqual([action for action, _ in refs], ["actions/checkout"])
        self.assertRegex(refs[0][1], r"^[0-9a-f]{40}$")


if __name__ == "__main__":
    unittest.main()
