import pathlib
import re
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "preserve-frozen-physical-handoff.yml"
CONTRACT_WORKFLOW = ROOT / ".github" / "workflows" / "frozen-preserve-contract-test.yml"
CHECKOUT_SHA = "3d3c42e5aac5ba805825da76410c181273ba90b1"

EXPECTED_ENV = {
    "ARTIFACT_ID": "11317304352",
    "ARTIFACT_RUN_ID": "37241768528",
    "EXPECTED_ARTIFACT_DIGEST": "867f2a75260c89d9d92416d407df5dc559a05d99d6f506006003b163ad3e51ce",
    "EXPECTED_ARTIFACT_SIZE_BYTES": "84450954",
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

    def test_production_python_runtime_is_pinned_and_isolated(self):
        for line in (
            "      LANG: C.UTF-8",
            "      LC_ALL: C.UTF-8",
            '      PYTHONHASHSEED: "1"',
            '      PYTHONNOUSERSITE: "1"',
            '      PYTHONDONTWRITEBYTECODE: "1"',
            "      TZ: UTC",
        ):
            with self.subTest(line=line):
                self.assertEqual(self.text.count(line), 1)

        self.assertEqual(
            len(re.findall(r'(?m)^\s+PYTHONNOUSERSITE:\s*', self.text)),
            1,
            "production preserve job must expose exactly one PYTHONNOUSERSITE binding",
        )
        self.assertEqual(
            self.text.count(
                'python3 -I -c \'import platform, sys; assert platform.python_implementation() == "CPython"; '
                'assert sys.version_info[:2] == (3, 12), sys.version\''
            ),
            1,
            "production preservation must fail before parsing if the VPS Python runtime drifts",
        )

    def test_every_production_python_process_uses_isolated_mode(self):
        invocations = self.text.count("python3 ")
        self.assertEqual(invocations, 9)
        self.assertEqual(
            self.text.count("python3 -I "),
            invocations,
            "every production Python process must ignore runner user/site/path injection",
        )

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
                "          GITHUB_TOKEN: ${{ github.token }}",
                "          GITHUB_TOKEN: ${{ github.token }}",
                "          GITHUB_TOKEN: ${{ github.token }}",
            ],
        )
        self.assertNotIn("persist-credentials:", self.text)

    def test_every_github_http_call_is_time_bounded(self):
        self.assertEqual(self.text.count('      CURL_CONNECT_TIMEOUT_SECONDS: "10"'), 1)
        self.assertEqual(self.text.count('      CURL_MAX_TIME_SECONDS: "120"'), 1)
        curl_calls = self.text.count("curl --connect-timeout")
        self.assertEqual(curl_calls, 6, "every GitHub HTTP call must use the bounded curl contract")
        self.assertEqual(
            self.text.count('--connect-timeout "$CURL_CONNECT_TIMEOUT_SECONDS"'),
            curl_calls,
        )
        self.assertEqual(
            self.text.count('--max-time "$CURL_MAX_TIME_SECONDS"'),
            curl_calls,
        )
        self.assertNotRegex(
            self.text,
            r"(?m)curl --(?!connect-timeout)",
            "no preservation curl call may bypass the per-request deadline",
        )

    def test_source_and_preserved_asset_sizes_are_bound_before_digest(self):
        self.assertEqual(
            self.text.count('      EXPECTED_ARTIFACT_SIZE_BYTES: "84450954"'),
            1,
        )
        source_size = '          actual_size="$(wc -c < "$archive" | tr -d \'[:space:]\')"'
        source_gate = '          test "$actual_size" = "$EXPECTED_ARTIFACT_SIZE_BYTES" || {'
        source_digest = '          actual_digest="$(sha256sum "$archive" | awk \'{print tolower($1)}\')"'
        preserved_size = '          verify_size="$(wc -c < "$verify" | tr -d \'[:space:]\')"'
        preserved_gate = '          test "$verify_size" = "$EXPECTED_ARTIFACT_SIZE_BYTES" || {'
        preserved_digest = '          actual_digest="$(sha256sum "$verify" | awk \'{print tolower($1)}\')"'

        for line in (
            source_size,
            source_gate,
            source_digest,
            preserved_size,
            preserved_gate,
            preserved_digest,
        ):
            with self.subTest(line=line):
                self.assertEqual(self.text.count(line), 1)

        self.assertLess(self.text.index(source_gate), self.text.index(source_digest))
        self.assertLess(self.text.index(preserved_gate), self.text.rindex(preserved_digest))

    def test_release_creation_stays_bound_to_frozen_source(self):
        self.assertIn('"target_commitish": os.environ["SOURCE_REVISION"]', self.text)
        self.assertIn('"tag_name": os.environ["RELEASE_TAG"]', self.text)
        self.assertIn('test "$actual_digest" = "$EXPECTED_ARTIFACT_DIGEST"', self.text)
        self.assertGreaterEqual(
            self.text.count("EXPECTED_ARTIFACT_DIGEST"),
            3,
        )


class FrozenPreserveContractWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.text = CONTRACT_WORKFLOW.read_text(encoding="utf-8")

    def test_contract_lane_runtime_and_checkout_are_pinned(self):
        self.assertIn("    runs-on: ubuntu-24.04", self.text)
        self.assertNotIn("ubuntu-latest", self.text)
        for line in (
            "      LANG: C.UTF-8",
            "      LC_ALL: C.UTF-8",
            '      PYTHONHASHSEED: "1"',
            '      PYTHONNOUSERSITE: "1"',
            '      PYTHONDONTWRITEBYTECODE: "1"',
            "      TZ: UTC",
        ):
            with self.subTest(line=line):
                self.assertEqual(self.text.count(line), 1)

        self.assertEqual(
            len(re.findall(r'(?m)^\s+PYTHONNOUSERSITE:\s*', self.text)),
            1,
            "contract lane must expose exactly one PYTHONNOUSERSITE binding",
        )

        refs = re.findall(
            r"^\s*(?:-\s*)?uses:\s*([^@\s]+)@([^\s#]+)",
            self.text,
            flags=re.MULTILINE,
        )
        self.assertEqual(refs, [("actions/checkout", CHECKOUT_SHA)])
        self.assertIn(
            f"uses: actions/checkout@{CHECKOUT_SHA} # v7.0.1 (node24)",
            self.text,
        )
        self.assertEqual(self.text.count("          persist-credentials: false"), 1)

    def test_contract_lane_pins_cpython_312_and_exact_head(self):
        self.assertIn(
            'python3 -c \'import platform, sys; assert platform.python_implementation() == "CPython"; assert sys.version_info[:2] == (3, 12), sys.version\'',
            self.text,
        )
        expression = "${{ github.event_name == 'pull_request' && github.event.pull_request.head.sha || github.sha }}"
        self.assertEqual(self.text.count(f"          ref: {expression}"), 1)
        self.assertEqual(self.text.count(f"          EXPECTED_SHA: {expression}"), 1)
        self.assertIn('          test "$(git rev-parse HEAD)" = "$EXPECTED_SHA"', self.text)

    def test_contract_lane_is_read_only_strict_and_self_guarding(self):
        self.assertRegex(
            self.text,
            r"(?ms)^permissions:\n  contents: read\n\nconcurrency:",
        )
        self.assertNotIn("continue-on-error: true", self.text)
        self.assertNotIn("secrets.", self.text)
        for path in (
            ".github/workflows/preserve-frozen-physical-handoff.yml",
            ".github/workflows/frozen-preserve-contract-test.yml",
            "tests/test_preserve_frozen_handoff_workflow.py",
        ):
            with self.subTest(path=path):
                self.assertEqual(self.text.count(f'      - "{path}"'), 2)

        lines = self.text.splitlines()
        run_indices = [i for i, line in enumerate(lines) if line == "        run: |"]
        self.assertEqual(len(run_indices), 3)
        for index in run_indices:
            self.assertEqual(lines[index + 1], "          set -euo pipefail")

        self.assertIn("- name: Verify worktree remains clean", self.text)
        for command in (
            "          git diff --exit-code -- .",
            "          git diff --cached --exit-code -- .",
            '          test -z "$(git ls-files --others --exclude-standard)"',
        ):
            with self.subTest(command=command):
                self.assertEqual(self.text.count(command), 1)


if __name__ == "__main__":
    unittest.main()
