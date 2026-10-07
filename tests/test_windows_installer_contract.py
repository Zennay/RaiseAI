import pathlib
import re
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "install-watch-windows.ps1"


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


if __name__ == "__main__":
    unittest.main()
