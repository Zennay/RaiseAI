import pathlib
import re
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "frozen-acceptance-tooling-test.yml"
START_GUIDE = ROOT / "START-HERE.md"
DEVICE_TEST_GUIDE = ROOT / "DEVICE-TEST.md"
FALLBACK_GUIDES = {
    "GEMINI-HOME-SETUP.md": "Fallback integration only.",
    "CHATGPT-WEB-SETUP.md": "Legacy fallback setup only.",
    "REMOTE-LOGIN.md": "Alleen voor de legacy ChatGPT Web-fallback.",
}
CHECKOUT_SHA = "3d3c42e5aac5ba805825da76410c181273ba90b1"


class FrozenAcceptanceToolingWorkflowContractTests(unittest.TestCase):
    def setUp(self):
        self.text = WORKFLOW.read_text(encoding="utf-8")

    def test_uses_pinned_node24_checkout_only(self):
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
        self.assertIn("persist-credentials: false", self.text)
        self.assertNotIn("pull_request_target:", self.text)

    def test_hosted_runtime_is_reproducible(self):
        self.assertIn("runs-on: ubuntu-24.04", self.text)
        self.assertNotIn("ubuntu-latest", self.text)
        for line in (
            "      LANG: C.UTF-8",
            "      LC_ALL: C.UTF-8",
            '      PYTHONHASHSEED: "1"',
            '      PYTHONNOUSERSITE: "1"',
            '      PYTHONDONTWRITEBYTECODE: "1"',
            "      PYTHONPYCACHEPREFIX: /tmp/raise-frozen-tooling-pyc",
            "      TZ: UTC",
        ):
            with self.subTest(line=line):
                self.assertEqual(self.text.count(line), 1)

    def test_python_user_site_is_disabled_once(self):
        lines = [line for line in self.text.splitlines() if re.match(r"^\s+PYTHONNOUSERSITE:", line)]
        self.assertEqual(lines, ['      PYTHONNOUSERSITE: "1"'])

    def test_python_runtime_is_explicitly_pinned(self):
        command = (
            '          python3 -c \'import platform, sys; '
            'assert platform.python_implementation() == "CPython"; '
            'assert sys.version_info[:2] == (3, 12), sys.version\''
        )
        self.assertEqual(self.text.count(command), 1)

    def test_explicit_py_compile_cannot_dirty_checkout(self):
        self.assertIn("python3 -m py_compile", self.text)
        self.assertEqual(
            self.text.count("      PYTHONPYCACHEPREFIX: /tmp/raise-frozen-tooling-pyc"),
            1,
        )
        self.assertIn("- name: Verify worktree remains clean", self.text)
        for command in (
            "          git diff --exit-code -- .",
            "          git diff --cached --exit-code -- .",
            '          test -z "$(git ls-files --others --exclude-standard)"',
        ):
            with self.subTest(command=command):
                self.assertEqual(self.text.count(command), 1)

    def test_release_carrier_token_scope_is_exact(self):
        token_lines = [
            line
            for line in self.text.splitlines()
            if re.match(r"^\s+GITHUB_TOKEN:\s*", line)
        ]
        self.assertEqual(
            token_lines,
            ["          GITHUB_TOKEN: ${{ github.token }}"],
            "only the frozen release-carrier step may receive the read-only GitHub token",
        )
        self.assertNotRegex(self.text, r"\$\{\{\s*secrets\.")

        lines = self.text.splitlines()
        start = lines.index("      - name: Frozen release carrier")
        following = [
            index
            for index, line in enumerate(lines)
            if index > start and line.startswith("      - name:")
        ]
        end = min(following) if following else len(lines)
        carrier_step = lines[start:end]
        self.assertIn("        env:", carrier_step)
        self.assertIn("          GITHUB_TOKEN: ${{ github.token }}", carrier_step)

    def test_release_carrier_drops_token_before_downloaded_launcher_exec(self):
        lines = self.text.splitlines()
        fetch = lines.index(
            '          python3 tools/fetch-frozen-physical-handoff.py --output "$output"'
        )
        unset_token = lines.index("          unset GITHUB_TOKEN")
        prove_unset = lines.index('          test -z "${GITHUB_TOKEN:-}"')
        launcher = lines.index(
            '            bash "$output/start-physical-handoff.command" --verify-only'
        )

        self.assertLess(fetch, unset_token)
        self.assertLess(unset_token, prove_unset)
        self.assertLess(prove_unset, launcher)
        self.assertEqual(self.text.count("          unset GITHUB_TOKEN"), 1)
        self.assertEqual(self.text.count('          test -z "${GITHUB_TOKEN:-}"'), 1)

    def test_permissions_are_read_only(self):
        self.assertRegex(
            self.text,
            r"(?ms)^permissions:\n  contents: read\n\nconcurrency:",
        )
        self.assertNotRegex(self.text, r"(?m)^    permissions:")

    def test_exact_head_checkout_remains_bound(self):
        expression = (
            "${{ github.event_name == 'pull_request' && "
            "github.event.pull_request.head.sha || github.sha }}"
        )
        self.assertIn(f"          ref: {expression}", self.text)
        self.assertIn(
            '          expected="${{ github.event_name == \'pull_request\' && github.event.pull_request.head.sha || github.sha }}"',
            self.text,
        )
        self.assertIn('          test "$revision" = "$expected"', self.text)

    def test_contract_test_is_triggered_and_executed(self):
        path = '      - "tests/test_frozen_acceptance_tooling_workflow.py"'
        self.assertEqual(
            self.text.count(path),
            2,
            "contract test must trigger both push and pull_request validation",
        )
        command = (
            "          python3 -m unittest discover -s tests "
            "-p 'test_frozen_acceptance_tooling_workflow.py'"
        )
        self.assertEqual(self.text.count(command), 1)

    def test_operator_start_guide_stays_bound_to_frozen_handoff(self):
        guide = START_GUIDE.read_text(encoding="utf-8")
        section = guide.split("## Preferred physical validation flow", 1)[1].split(
            "\n## 1. Install or upgrade the Watch app", 1
        )[0]

        self.assertIn(
            "8f719bb273f9b997848864f342598e7df5f090e5",
            section,
            "current physical gate must name the preserved v1.5.2 source revision",
        )
        self.assertIn(
            "bash ./start-frozen-acceptance.command --preflight-only /path/to/watch-gateway.properties",
            section,
        )
        self.assertIn(
            "bash ./start-frozen-acceptance.command /path/to/watch-gateway.properties",
            section,
        )
        self.assertIn(
            "Do not run `physical-validation.command all` from the current checkout",
            section,
        )
        self.assertNotIn(
            "bash ./physical-validation.command all /path/to/watch-gateway.properties",
            section,
            "repository-tip builds must not be presented as the current frozen acceptance path",
        )

    def test_operator_start_guide_triggers_frozen_tooling_contract(self):
        path = '      - "START-HERE.md"'
        self.assertEqual(
            self.text.count(path),
            2,
            "operator handoff guide changes must trigger both push and pull_request validation",
        )

    def test_legacy_device_checklist_cannot_pose_as_current_acceptance(self):
        guide = DEVICE_TEST_GUIDE.read_text(encoding="utf-8")
        self.assertIn("Historical fallback checklist only.", guide)
        self.assertIn(
            "8f719bb273f9b997848864f342598e7df5f090e5",
            guide,
        )
        self.assertIn("start-frozen-acceptance.command", guide)
        self.assertIn("Do not use this V0.3 Gemini-first checklist", guide)

    def test_legacy_device_checklist_triggers_frozen_tooling_contract(self):
        self.assertEqual(
            self.text.count('      - "DEVICE-TEST.md"'),
            2,
            "legacy checklist warning changes must trigger both push and pull_request validation",
        )

    def test_legacy_fallback_guides_cannot_pose_as_current_acceptance(self):
        for path, warning in FALLBACK_GUIDES.items():
            with self.subTest(path=path):
                guide = (ROOT / path).read_text(encoding="utf-8")
                self.assertIn(warning, guide)
                self.assertIn("8f719bb273f9b997848864f342598e7df5f090e5", guide)
                self.assertIn("start-frozen-acceptance.command", guide)

    def test_legacy_fallback_guides_trigger_frozen_tooling_contract(self):
        for path in FALLBACK_GUIDES:
            with self.subTest(path=path):
                self.assertEqual(
                    self.text.count(f'      - "{path}"'),
                    2,
                    f"{path} changes must trigger both push and pull_request validation",
                )

    def test_all_run_steps_fail_closed_under_bash(self):
        lines = self.text.splitlines()
        run_indices = [
            index for index, line in enumerate(lines)
            if line == "        run: |"
        ]
        self.assertTrue(run_indices)
        for index in run_indices:
            with self.subTest(run_line=index + 1):
                self.assertEqual(lines[index + 1], "          set -euo pipefail")
        self.assertNotIn("continue-on-error: true", self.text)


if __name__ == "__main__":
    unittest.main()
