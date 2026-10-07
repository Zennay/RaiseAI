import json
import os
import subprocess
import tempfile
import textwrap
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class LoginFromMacContractTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.bin = self.root / "bin"
        self.bin.mkdir()
        self.trace = self.root / "trace.log"
        self.script = ROOT / "login-from-mac.command"

        adb = self.bin / "adb"
        adb.write_text(
            textwrap.dedent(
                """\
                #!/usr/bin/env python3
                import json
                import os
                import sys
                from pathlib import Path

                args = sys.argv[1:]
                trace = Path(os.environ["FAKE_TRACE"])
                with trace.open("a", encoding="utf-8") as handle:
                    handle.write("adb " + json.dumps(args) + "\\n")

                connected = [item for item in os.environ.get("FAKE_CONNECTED", "").split(",") if item]
                watches = set(item for item in os.environ.get("FAKE_WATCHES", "").split(",") if item)

                if args == ["devices"]:
                    exit_code = int(os.environ.get("FAKE_ADB_DEVICES_EXIT", "0"))
                    if exit_code:
                        print("simulated adb enumeration failure")
                        sys.exit(exit_code)
                    print("List of devices attached")
                    for serial in connected:
                        print(f"{serial}\\tdevice")
                    sys.exit(0)

                if len(args) >= 3 and args[0] == "-s":
                    serial = args[1]
                    command = args[2:]
                    if serial not in connected:
                        sys.exit(1)
                    if command == ["shell", "getprop", "ro.build.characteristics"]:
                        print("watch" if serial in watches else "phone")
                        sys.exit(0)
                    if command == ["shell", "getprop", "ro.product.model"]:
                        print("SM-L315F" if serial in watches else "Pixel 9")
                        sys.exit(0)
                    if command == ["get-state"]:
                        print("device")
                        sys.exit(0)
                    if command[:3] == ["shell", "am", "start"]:
                        sys.exit(int(os.environ.get("FAKE_AM_START_EXIT", "0")))

                sys.exit(2)
                """
            ),
            encoding="utf-8",
        )
        adb.chmod(0o755)

        scrcpy = self.bin / "scrcpy"
        scrcpy.write_text(
            textwrap.dedent(
                """\
                #!/usr/bin/env python3
                import json
                import os
                import sys
                from pathlib import Path

                trace = Path(os.environ["FAKE_TRACE"])
                with trace.open("a", encoding="utf-8") as handle:
                    handle.write("scrcpy " + json.dumps(sys.argv[1:]) + "\\n")
                """
            ),
            encoding="utf-8",
        )
        scrcpy.chmod(0o755)

    def tearDown(self):
        self.temp.cleanup()

    def run_script(self, *args, connected="", watches="", **overrides):
        env = os.environ.copy()
        env["PATH"] = str(self.bin) + os.pathsep + env.get("PATH", "")
        env["HOME"] = str(self.root)
        env["FAKE_TRACE"] = str(self.trace)
        env["FAKE_CONNECTED"] = connected
        env["FAKE_WATCHES"] = watches
        env.pop("ANDROID_SERIAL", None)
        for key, value in overrides.items():
            env[key] = str(value)
        return subprocess.run(
            [str(self.script), *args],
            cwd=self.root,
            env=env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )

    def trace_text(self):
        return self.trace.read_text(encoding="utf-8") if self.trace.exists() else ""

    def test_rejects_unexpected_arguments_before_adb(self):
        result = self.run_script("unexpected")
        self.assertEqual(result.returncode, 2, result.stdout)
        self.assertIn("Usage: ./login-from-mac.command", result.stdout)
        self.assertEqual(self.trace_text(), "")

    def test_reports_adb_enumeration_failure(self):
        result = self.run_script(FAKE_ADB_DEVICES_EXIT=7)
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("ADB device enumeration failed.", result.stdout)
        self.assertIn("simulated adb enumeration failure", result.stdout)
        self.assertNotIn("\"shell\", \"am\", \"start\"", self.trace_text())

    def test_automatically_selects_only_expected_watch(self):
        result = self.run_script(connected="phone-1,watch-1", watches="watch-1")
        self.assertEqual(result.returncode, 0, result.stdout)
        trace = self.trace_text()
        self.assertIn('adb ["-s", "watch-1", "shell", "am", "start"', trace)
        self.assertIn('scrcpy ["-s", "watch-1", "--window-title", "Raise AI · Watch login"]', trace)
        self.assertNotIn('adb ["-s", "phone-1", "shell", "am", "start"', trace)

    def test_rejects_ambiguous_watch_selection(self):
        result = self.run_script(connected="watch-1,watch-2", watches="watch-1,watch-2")
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("Meerdere Galaxy Watch 7-apparaten gevonden", result.stdout)
        self.assertNotIn("\"shell\", \"am\", \"start\"", self.trace_text())

    def test_explicit_android_serial_binds_exact_watch(self):
        result = self.run_script(
            connected="watch-1,watch-2",
            watches="watch-1,watch-2",
            ANDROID_SERIAL="watch-2",
        )
        self.assertEqual(result.returncode, 0, result.stdout)
        trace = self.trace_text()
        self.assertIn('adb ["-s", "watch-2", "shell", "am", "start"', trace)
        self.assertIn('scrcpy ["-s", "watch-2", "--window-title", "Raise AI · Watch login"]', trace)
        self.assertNotIn('adb ["-s", "watch-1", "shell", "am", "start"', trace)

    def test_rejects_disconnected_explicit_target(self):
        result = self.run_script(
            connected="watch-1",
            watches="watch-1",
            ANDROID_SERIAL="watch-2",
        )
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("Prepared Galaxy Watch 7 is not connected over ADB: watch-2", result.stdout)
        self.assertNotIn("\"shell\", \"am\", \"start\"", self.trace_text())

    def test_rejects_explicit_non_watch_target(self):
        result = self.run_script(
            connected="phone-1",
            watches="",
            ANDROID_SERIAL="phone-1",
        )
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("not the expected Galaxy Watch 7", result.stdout)
        self.assertNotIn("\"shell\", \"am\", \"start\"", self.trace_text())

    def test_launch_failure_does_not_start_scrcpy(self):
        result = self.run_script(
            connected="watch-1",
            watches="watch-1",
            FAKE_AM_START_EXIT=9,
        )
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("Kon Raise AI login niet openen", result.stdout)
        self.assertNotIn("scrcpy ", self.trace_text())


class LoginFromMacWorkflowContractTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.workflow = (
            ROOT / ".github" / "workflows" / "login-from-mac-quality.yml"
        ).read_text(encoding="utf-8")

    def test_workflow_is_self_hosted_read_only_and_pinned(self):
        self.assertIn("    runs-on: [self-hosted, linux, x64, vps-bb300bba]", self.workflow)
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
            "login-from-mac.command",
            "tests/test_login_from_mac_contract.py",
            ".github/workflows/login-from-mac-quality.yml",
        ):
            with self.subTest(path=path):
                self.assertEqual(self.workflow.count(f'      - "{path}"'), 2)
        self.assertIn("  push:\n    branches:\n      - main\n    paths:", self.workflow)
        self.assertIn("  pull_request:\n    paths:", self.workflow)

    def test_workflow_binds_exact_head_runner_and_clean_tree(self):
        self.assertIn(
            "EXPECTED_SHA: ${{ github.event_name == 'pull_request' && "
            "github.event.pull_request.head.sha || github.sha }}",
            self.workflow,
        )
        self.assertIn('          test "$(hostname)" = "vps-bb300bba"', self.workflow)
        self.assertIn('          test "$(git rev-parse HEAD)" = "$EXPECTED_SHA"', self.workflow)
        self.assertGreaterEqual(
            self.workflow.count('test -z "$(git status --porcelain --untracked-files=normal)"'),
            2,
        )
        self.assertEqual(self.workflow.count("          set -euo pipefail"), 2)


if __name__ == "__main__":
    unittest.main()
