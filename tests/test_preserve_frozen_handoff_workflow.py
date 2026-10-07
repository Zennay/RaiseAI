import pathlib
import re
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "preserve-frozen-physical-handoff.yml"

EXPECTED_ENV = {
    "ARTIFACT_ID": "11317304352",
    "ARTIFACT_RUN_ID": "37241768528",
    "EXPECTED_ARTIFACT_DIGEST": "867f2a75260c89d9d92416d407df5dc559a05d99d6f506006003b163ad3e51ce",
    "SOURCE_REVISION": "8f719bb273f9b997848864f342598e7df5f090e5",
    "RELEASE_TAG": "physical-handoff-v1.5.2-8f719bb",
    "ASSET_NAME": "RaiseAI-Watch7-v1.5.2-physical-handoff-37241768528.zip",
    "HANDOFF_NAME": "RaiseAI-Watch7-v1.5.2-physical-handoff-37241768528",
}


class PreserveFrozenHandoffWorkflowContractTests(unittest.TestCase):
    def setUp(self):
        self.text = WORKFLOW.read_text(encoding="utf-8")
        self.lines = self.text.splitlines()

    def test_trigger_surface_cannot_expand_to_untrusted_events(self):
        self.assertIn("  workflow_dispatch:", self.lines)
        self.assertIn("  push:", self.lines)
        self.assertNotIn("  pull_request:", self.lines)
        self.assertNotIn("  pull_request_target:", self.lines)
        self.assertNotIn("  schedule:", self.lines)
        self.assertNotIn("  repository_dispatch:", self.lines)
        self.assertIn("      - main", self.lines)
        self.assertEqual(
            self.text.count('      - ".github/workflows/preserve-frozen-physical-handoff.yml"'),
            1,
        )

    def test_write_permissions_are_narrow_and_explicit(self):
        match = re.search(
            r"(?ms)^permissions:\n((?:  [^\n]+\n)+)",
            self.text,
        )
        self.assertIsNotNone(match)
        self.assertEqual(
            match.group(1).splitlines(),
            ["  actions: read", "  contents: write"],
        )
        self.assertNotRegex(self.text, r"(?m)^    permissions:")
        self.assertNotRegex(self.text, r"\$\{\{\s*secrets\.")

    def test_job_is_bound_to_vps_and_cannot_cancel_previous_preservation(self):
        self.assertIn("    runs-on: [self-hosted, vps-bb300bba]", self.text)
        self.assertIn("    timeout-minutes: 10", self.text)
        self.assertIn("  cancel-in-progress: false", self.text)
        self.assertNotIn("ubuntu-latest", self.text)

    def test_frozen_identity_constants_are_exact_and_unique(self):
        for key, value in EXPECTED_ENV.items():
            with self.subTest(key=key):
                line = f'      {key}: "{value}"'
                self.assertEqual(
                    self.text.count(line),
                    1,
                    f"{key} must stay bound exactly once to the frozen v1.5.2 carrier",
                )

    def test_no_external_actions_expand_execution_surface(self):
        self.assertNotRegex(self.text, r"(?m)^\s*(?:-\s*)?uses:")
        self.assertNotIn("actions/checkout@", self.text)

    def test_every_run_step_is_explicit_strict_bash(self):
        step_starts = [
            index for index, line in enumerate(self.lines)
            if line.startswith("      - name:")
        ]
        self.assertEqual(len(step_starts), 3)
        for position, start in enumerate(step_starts):
            end = step_starts[position + 1] if position + 1 < len(step_starts) else len(self.lines)
            step = self.lines[start:end]
            with self.subTest(step=self.lines[start]):
                self.assertIn("        shell: bash", step)
                run_index = step.index("        run: |")
                self.assertEqual(step[run_index + 1], "          set -euo pipefail")

    def test_only_github_token_is_exposed_to_mutating_steps(self):
        token_lines = [
            line for line in self.lines
            if re.match(r"^\s+GITHUB_TOKEN:", line)
        ]
        self.assertEqual(
            token_lines,
            [
                "          GITHUB_TOKEN: \${{ github.token }}",
                "          GITHUB_TOKEN: \${{ github.token }}",
                "          GITHUB_TOKEN: \${{ github.token }}",
            ],
        )
        self.assertNotIn("persist-credentials:", self.text)

    def test_release_creation_stays_bound_to_frozen_source(self):
        self.assertIn('"target_commitish": os.environ["SOURCE_REVISION"]', self.text)
        self.assertIn('"tag_name": os.environ["RELEASE_TAG"]', self.text)
        self.assertIn('test "$actual_digest" = "$EXPECTED_ARTIFACT_DIGEST"', self.text)
        self.assertGreaterEqual(
            self.text.count("EXPECTED_ARTIFACT_DIGEST"),
            3,
        )


if __name__ == "__main__":
    unittest.main()
