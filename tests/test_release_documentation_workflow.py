import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "release-documentation-identity.yml"
CHECKOUT_SHA = "3d3c42e5aac5ba805825da76410c181273ba90b1"  # v7.0.1, node24


class ReleaseDocumentationWorkflowContractTests(unittest.TestCase):
    def setUp(self):
        self.text = WORKFLOW.read_text(encoding="utf-8")

    def test_hosted_python_runtime_is_reproducible(self):
        for line in (
            "      LANG: C.UTF-8",
            "      LC_ALL: C.UTF-8",
            '      PYTHONHASHSEED: "1"',
            '      PYTHONNOUSERSITE: "1"',
            '      PYTHONDONTWRITEBYTECODE: "1"',
            "      PYTHONPYCACHEPREFIX: /tmp/raise-release-doc-pyc",
            "      TZ: UTC",
        ):
            with self.subTest(line=line):
                self.assertEqual(self.text.count(line), 1)

        runtime = (
            '          python3 -c \'import platform, sys; '
            'assert platform.python_implementation() == "CPython"; '
            'assert sys.version_info[:2] == (3, 12), sys.version\''
        )
        self.assertEqual(self.text.count(runtime), 1)
        self.assertEqual(self.text.count("    runs-on: ubuntu-24.04"), 1)
        self.assertNotIn("ubuntu-latest", self.text)

    def test_external_action_surface_is_exact_and_immutable(self):
        refs = re.findall(
            r"^\s*(?:-\s*)?uses:\s*([^@\s]+)@([^\s#]+)",
            self.text,
            flags=re.MULTILINE,
        )
        self.assertEqual(refs, [("actions/checkout", CHECKOUT_SHA)])
        self.assertRegex(refs[0][1], r"^[0-9a-f]{40}$")
        self.assertIn(
            f"uses: actions/checkout@{CHECKOUT_SHA} # v7.0.1 (node24)",
            self.text,
        )

    def test_checkout_is_exact_head_and_credential_free(self):
        expression = "${{ github.event.pull_request.head.sha || github.sha }}"
        self.assertEqual(self.text.count(f"          ref: {expression}"), 1)
        self.assertEqual(
            self.text.count(f"          EXPECTED_SHA: {expression}"),
            1,
        )
        self.assertEqual(self.text.count("          persist-credentials: false"), 1)
        self.assertIn('          test "$(git rev-parse HEAD)" = "$EXPECTED_SHA"', self.text)

    def test_permissions_are_exactly_read_only(self):
        block = re.search(
            r"(?ms)^permissions:\n((?:  [^\n]+\n)+)",
            self.text,
        )
        self.assertIsNotNone(block)
        self.assertEqual(block.group(1).splitlines(), ["  contents: read"])
        self.assertNotRegex(self.text, r"(?m)^    permissions:")

    def test_pull_request_dependencies_are_complete(self):
        expected = [
            "VERSION.txt",
            "README.md",
            "START-HERE.md",
            "PHYSICAL-ACCEPTANCE.md",
            "DEVICE-TEST.md",
            "REMOTE-LOGIN.md",
            "GEMINI-HOME-SETUP.md",
            "CHATGPT-WEB-SETUP.md",
            "tests/test_release_documentation_identity.py",
            "tests/test_release_documentation_workflow.py",
            ".github/workflows/release-documentation-identity.yml",
        ]
        lines = self.text.splitlines()
        start = lines.index("  pull_request:") + 1
        body = []
        for line in lines[start:]:
            if line and not line.startswith("    "):
                break
            body.append(line)
        self.assertIn("    paths:", body)
        paths_start = body.index("    paths:") + 1
        paths = []
        for line in body[paths_start:]:
            match = re.fullmatch(r'      - "([^"]+)"', line)
            if not match:
                break
            paths.append(match.group(1))
        self.assertEqual(paths, expected)

    def test_contract_test_executes_in_the_release_lane(self):
        self.assertEqual(
            self.text.count("python3 -m unittest tests.test_release_documentation_identity tests.test_release_documentation_workflow"),
            1,
        )

    def test_run_steps_fail_closed_under_bash(self):
        lines = self.text.splitlines()
        step_starts = [
            index
            for index, line in enumerate(lines)
            if line.startswith("      - name:")
        ]
        run_indices = [
            index
            for index, line in enumerate(lines)
            if line == "        run: |"
        ]
        self.assertTrue(run_indices)
        self.assertNotIn("continue-on-error: true", self.text)
        for run_index in run_indices:
            with self.subTest(line=run_index + 1):
                step_start = max(i for i in step_starts if i < run_index)
                following = [i for i in step_starts if i > step_start]
                step_end = min(following) if following else len(lines)
                step = lines[step_start:step_end]
                self.assertIn("        shell: bash", step)
                self.assertEqual(lines[run_index + 1], "          set -euo pipefail")

    def test_workflow_is_bounded_hosted_and_secret_free(self):
        self.assertIn("runs-on: ubuntu-24.04", self.text)
        self.assertIn("timeout-minutes: 5", self.text)
        self.assertNotIn("self-hosted", self.text)
        self.assertNotIn("pull_request_target:", self.text)
        self.assertNotRegex(self.text, r"\$\{\{\s*secrets\.")


if __name__ == "__main__":
    unittest.main()
