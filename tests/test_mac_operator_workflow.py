from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "mac-adb-autoconnect-contract.yml"
CHECKOUT_SHA = "3d3c42e5aac5ba805825da76410c181273ba90b1"


class MacOperatorWorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = WORKFLOW.read_text(encoding="utf-8")

    def test_is_hosted_read_only_exact_head_and_credential_free(self):
        self.assertEqual(self.text.count("    runs-on: ubuntu-24.04"), 1)
        self.assertNotIn("self-hosted", self.text)
        self.assertNotIn("vps-bb300bba", self.text)
        self.assertIn("permissions:\n  contents: read\n", self.text)
        self.assertNotIn("pull_request_target:", self.text)
        self.assertNotRegex(self.text, r"\$\{\{\s*secrets\.")
        self.assertNotIn("continue-on-error: true", self.text)

        refs = re.findall(
            r"^\s*(?:-\s*)?uses:\s*([^@\s]+)@([^\s#]+)",
            self.text,
            flags=re.MULTILINE,
        )
        self.assertEqual(refs, [("actions/checkout", CHECKOUT_SHA)])

        exact_head = (
            "${{ github.event_name == 'pull_request' && "
            "github.event.pull_request.head.sha || github.sha }}"
        )
        self.assertEqual(self.text.count(f"          ref: {exact_head}"), 1)
        self.assertEqual(self.text.count(f"          EXPECTED_SHA: {exact_head}"), 1)
        self.assertEqual(self.text.count("          persist-credentials: false"), 1)

    def test_runtime_environment_and_execution_are_deterministic(self):
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

        runtime = (
            '          python3 -c \'import platform, sys; '
            'assert platform.python_implementation() == "CPython"; '
            'assert sys.version_info[:2] == (3, 12), sys.version\''
        )
        self.assertEqual(self.text.count(runtime), 1)
        for command in (
            "          bash -n install-mac-adb-autoconnect.command login-from-mac.command",
            "          python3 -m unittest tests.test_mac_adb_autoconnect_contract tests.test_mac_watch_login_contract tests.test_mac_operator_workflow",
            "          git diff --exit-code -- .",
            "          git diff --cached --exit-code -- .",
            '          test -z "$(git ls-files --others --exclude-standard)"',
        ):
            with self.subTest(command=command):
                self.assertEqual(self.text.count(command), 1)

    def test_push_and_pull_request_triggers_cover_every_contract_input(self):
        expected = (
            "install-mac-adb-autoconnect.command",
            "login-from-mac.command",
            "tests/test_mac_adb_autoconnect_contract.py",
            "tests/test_mac_watch_login_contract.py",
            "tests/test_mac_operator_workflow.py",
            ".github/workflows/mac-adb-autoconnect-contract.yml",
        )
        for path in expected:
            with self.subTest(path=path):
                self.assertEqual(self.text.count(f'      - "{path}"'), 2)


if __name__ == "__main__":
    unittest.main()
