import pathlib
import re
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "install-watch-windows.ps1"
WORKFLOW = ROOT / ".github" / "workflows" / "windows-installer-quality.yml"


class WindowsInstallerContractTests(unittest.TestCase):
    def setUp(self):
        self.script = SCRIPT.read_text(encoding="utf-8")

    def test_rejects_ambiguous_versioned_apk_artifacts(self):
        self.assertIn("function Get-SingleApkCandidate", self.script)
        self.assertRegex(
            self.script,
            re.compile(
                r"\$versioned\.Count -gt 1\).*?Meerdere Raise AI APK-kandidaten",
                re.DOTALL,
            ),
        )
        self.assertNotIn("Where-Object { $_.Name -match '^RaiseAI-v.+-debug\\.apk$' } | Select-Object -First 1", self.script)

    def test_rejects_ambiguous_fallback_apk_artifacts(self):
        self.assertRegex(
            self.script,
            re.compile(
                r"\$fallback\.Count -gt 1\).*?Meerdere app-debug\.apk-kandidaten",
                re.DOTALL,
            ),
        )

    def test_explicit_watch_must_be_connected_after_adb_connect(self):
        connect = self.script.index('adb connect $Watch')
        devices = self.script.index('$deviceOutput = @(adb devices)')
        membership = self.script.index('$deviceLines -notcontains $Watch')
        selection = self.script.index('$serial = $Watch')

        self.assertLess(connect, devices)
        self.assertLess(devices, membership)
        self.assertLess(membership, selection)
        self.assertIn('throw "ADB connect naar $Watch is mislukt."', self.script)

    def test_adb_device_enumeration_failure_is_fatal(self):
        devices = self.script.index('$deviceOutput = @(adb devices)')
        error_check = self.script.index('throw "Kon de ADB device-lijst niet lezen."', devices)
        selection = self.script.index('if ($Watch) {', devices)

        self.assertLess(devices, error_check)
        self.assertLess(error_check, selection)

    def test_wear_identity_abi_launch_and_status_fail_closed(self):
        self.assertIn('$LASTEXITCODE -ne 0 -or -not $watchFeature', self.script)
        self.assertIn('$LASTEXITCODE -ne 0 -or -not $abi', self.script)
        self.assertIn('throw "Raise AI kon na installatie niet worden gestart."', self.script)
        self.assertIn('throw "Kon de geinstalleerde Raise AI pakketstatus niet uitlezen."', self.script)


class WindowsInstallerWorkflowContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.workflow = WORKFLOW.read_text(encoding="utf-8")

    def test_workflow_is_read_only_exact_head_and_runner_bound(self):
        self.assertIn("permissions:\n  contents: read", self.workflow)
        self.assertIn(
            "    runs-on: [self-hosted, linux, x64, vps-bb300bba]",
            self.workflow,
        )
        self.assertIn('      PYTHONDONTWRITEBYTECODE: "1"', self.workflow)
        self.assertIn(
            "uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1",
            self.workflow,
        )
        exact_head = "${{ github.event_name == 'pull_request' && github.event.pull_request.head.sha || github.sha }}"
        self.assertEqual(self.workflow.count(f"          ref: {exact_head}"), 1)
        self.assertEqual(self.workflow.count(f"          EXPECTED_SHA: {exact_head}"), 1)
        self.assertIn("          persist-credentials: false", self.workflow)
        self.assertIn(
            '          test "$(hostname)" = "vps-bb300bba"',
            self.workflow,
        )
        self.assertIn(
            '          test "$(git rev-parse HEAD)" = "$EXPECTED_SHA"',
            self.workflow,
        )
        self.assertNotIn("pull_request_target:", self.workflow)
        self.assertNotIn("secrets.", self.workflow)
        self.assertNotIn("continue-on-error: true", self.workflow)

    def test_workflow_run_steps_are_strict_and_leave_clean_worktree(self):
        self.assertEqual(self.workflow.count("        shell: bash"), 2)
        self.assertEqual(self.workflow.count("        run: |"), 2)
        self.assertEqual(self.workflow.count("          set -euo pipefail"), 2)
        for command in (
            "          python3 -m unittest tests/test_windows_installer_contract.py -v",
            "          git diff --exit-code -- .",
            "          git diff --cached --exit-code -- .",
            '          test -z "$(git ls-files --others --exclude-standard)"',
        ):
            with self.subTest(command=command):
                self.assertIn(command, self.workflow)

    def test_workflow_triggers_on_every_owned_input(self):
        for path in (
            "install-watch-windows.ps1",
            "tests/test_windows_installer_contract.py",
            ".github/workflows/windows-installer-quality.yml",
        ):
            with self.subTest(path=path):
                self.assertEqual(
                    self.workflow.count(f'      - "{path}"'),
                    2,
                    f"{path} must trigger both push and pull_request validation",
                )


if __name__ == "__main__":
    unittest.main()
