import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import textwrap
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REVISION = "8f719bb273f9b997848864f342598e7df5f090e5"
APK_BYTES = b"synthetic-installed-raise-ai-apk"
APK_SHA = hashlib.sha256(APK_BYTES).hexdigest()
BOOT_ID = "11111111-2222-3333-4444-555555555555"


class RecoverySnapshotCommandTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.repo = self.root / "repo"
        self.repo.mkdir()
        self.bin = self.root / "bin"
        self.bin.mkdir()
        self.session = self.root / "session"
        self.session.mkdir()
        self.verifier_log = self.root / "verifier.log"

        shutil.copy2(
            ROOT / "watch-recovery-snapshot.command",
            self.repo / "watch-recovery-snapshot.command",
        )
        tools = self.repo / "tools"
        tools.mkdir()
        verifier = tools / "verify-watch-apk-identity.py"
        verifier.write_text(
            textwrap.dedent(
                """
                import os
                import sys
                from pathlib import Path

                log = Path(os.environ["VERIFIER_LOG"])
                log.write_text("\\n".join(sys.argv[1:]) + "\\n", encoding="utf-8")
                raise SystemExit(0)
                """
            ).lstrip(),
            encoding="utf-8",
        )

        self._write_session(APK_SHA)

        adb = self.bin / "adb"
        adb.write_text(
            textwrap.dedent(
                r"""#!/bin/bash
                set -euo pipefail

                if [ "${1:-}" = "start-server" ]; then
                  exit 0
                fi

                if [ "${1:-}" = "devices" ]; then
                  printf 'List of devices attached\nwatch-a\tdevice\n'
                  exit 0
                fi

                if [ "${1:-}" = "-s" ]; then
                  serial="$2"
                  shift 2
                  [ "$serial" = "watch-a" ] || {
                    echo "unexpected serial: $serial" >&2
                    exit 90
                  }

                  if [ "${1:-}" = "shell" ]; then
                    shift
                    case "$*" in
                      "getprop ro.product.model")
                        echo "SM_L315F"
                        ;;
                      "getprop ro.build.characteristics")
                        echo "watch"
                        ;;
                      "pm list features")
                        echo "feature:android.hardware.type.watch"
                        ;;
                      "dumpsys package nl.zennay.raiseai")
                        printf '  versionCode=152\n  versionName=1.5.2\n'
                        ;;
                      "pm path nl.zennay.raiseai")
                        echo "package:/data/app/raiseai/base.apk"
                        ;;
                      "cat /proc/sys/kernel/random/boot_id")
                        echo "11111111-2222-3333-4444-555555555555"
                        ;;
                      "cat /proc/uptime")
                        echo "123.45 67.89"
                        ;;
                      "dumpsys activity services nl.zennay.raiseai")
                        echo "ServiceRecord{abc nl.zennay.raiseai/.GestureMonitorService}"
                        ;;
                      *)
                        echo "unexpected shell invocation: $*" >&2
                        exit 91
                        ;;
                    esac
                    exit 0
                  fi

                  if [ "${1:-}" = "exec-out" ]; then
                    shift
                    case "$*" in
                      "cat /data/app/raiseai/base.apk")
                        printf 'synthetic-installed-raise-ai-apk'
                        ;;
                      "run-as nl.zennay.raiseai cat shared_prefs/raise_ai_prefs.xml")
                        cat <<'EOF_PREFS'
<?xml version='1.0' encoding='utf-8' standalone='yes' ?>
<map>
    <boolean name="monitoring_enabled" value="true" />
    <boolean name="calibrated" value="true" />
</map>
EOF_PREFS
                        ;;
                      *)
                        echo "unexpected exec-out invocation: $*" >&2
                        exit 92
                        ;;
                    esac
                    exit 0
                  fi
                fi

                echo "unexpected adb invocation: $*" >&2
                exit 93
                """
            ).lstrip(),
            encoding="utf-8",
        )
        adb.chmod(0o755)

    def tearDown(self):
        self.temp.cleanup()

    def _write_session(self, apk_sha):
        payload = {
            "schema_version": 1,
            "watch_serial": "watch-a",
            "watch_model": "SM_L315F",
            "app_version": "1.5.2",
            "source_revision": REVISION,
            "installed_apk_sha256": apk_sha,
        }
        (self.session / "session.json").write_text(
            json.dumps(payload),
            encoding="utf-8",
        )

    def run_snapshot(self, label="after"):
        env = os.environ.copy()
        env["PATH"] = f"{self.bin}:{env['PATH']}"
        env["VERIFIER_LOG"] = str(self.verifier_log)
        return subprocess.run(
            [
                "bash",
                str(self.repo / "watch-recovery-snapshot.command"),
                label,
                str(self.session),
            ],
            cwd=self.repo,
            env=env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )

    def test_captures_bound_watch_apk_preferences_boot_and_service_state(self):
        result = self.run_snapshot()

        self.assertEqual(result.returncode, 0, result.stdout)
        output = self.session / "recovery-after.json"
        self.assertTrue(output.is_file())
        data = json.loads(output.read_text(encoding="utf-8"))
        self.assertEqual(data["watch_serial"], "watch-a")
        self.assertEqual(data["watch_model"], "SM_L315F")
        self.assertEqual(data["app_version"], "1.5.2")
        self.assertEqual(data["source_revision"], REVISION)
        self.assertEqual(data["installed_apk_sha256"], APK_SHA)
        self.assertEqual(data["boot_id"], BOOT_ID)
        self.assertEqual(data["uptime_seconds"], 123.45)
        self.assertTrue(data["monitoring_enabled"])
        self.assertTrue(data["calibrated"])
        self.assertTrue(data["gesture_monitor_service_running"])
        self.assertTrue(data["read_only_capture"])

        verifier_args = self.verifier_log.read_text(encoding="utf-8")
        self.assertIn("--expect-source-revision", verifier_args)
        self.assertIn(REVISION, verifier_args)
        self.assertIn("--expect-sha256", verifier_args)
        self.assertIn(APK_SHA, verifier_args)

    def test_rejects_on_device_apk_digest_mismatch_before_snapshot(self):
        self._write_session("0" * 64)
        result = self.run_snapshot("mismatch")

        self.assertNotEqual(result.returncode, 0)
        self.assertIn(
            "Installed on-device APK SHA-256 does not match session identity.",
            result.stdout,
        )
        self.assertFalse((self.session / "recovery-mismatch.json").exists())
        self.assertFalse(self.verifier_log.exists())

    def test_refuses_to_overwrite_existing_snapshot(self):
        first = self.run_snapshot("repeat")
        self.assertEqual(first.returncode, 0, first.stdout)

        second = self.run_snapshot("repeat")
        self.assertNotEqual(second.returncode, 0)
        self.assertIn("Recovery snapshot already exists", second.stdout)


if __name__ == "__main__":
    unittest.main()
