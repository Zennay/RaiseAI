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


class WatchStabilitySnapshotCommandTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.repo = self.root / "repo"
        self.repo.mkdir()
        self.bin = self.root / "bin"
        self.bin.mkdir()
        self.session = self.root / "session"
        self.session.mkdir()

        shutil.copy2(
            ROOT / "watch-stability-snapshot.command",
            self.repo / "watch-stability-snapshot.command",
        )
        tools = self.repo / "tools"
        tools.mkdir()
        shutil.copy2(
            ROOT / "tools" / "analyze-watch-exit-info.py",
            tools / "analyze-watch-exit-info.py",
        )
        (tools / "verify-watch-apk-identity.py").write_text(
            "raise SystemExit(0)\n",
            encoding="utf-8",
        )

        (self.session / "session.json").write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "started_at_utc": "2026-10-05T05:00:00Z",
                    "app_version": "1.5.2",
                    "source_revision": REVISION,
                    "watch_model": "SM_L315F",
                    "watch_serial": "watch-a",
                    "installed_apk_sha256": APK_SHA,
                }
            ),
            encoding="utf-8",
        )

        self.adb = self.bin / "adb"
        self._write_adb(reason=10, reason_label="USER REQUESTED", status=0, service=True)

    def tearDown(self):
        self.temp.cleanup()

    def _write_adb(self, *, reason, reason_label, status, service):
        service_line = (
            "ServiceRecord{abc nl.zennay.raiseai/.GestureMonitorService}"
            if service
            else "No services"
        )
        self.adb.write_text(
            textwrap.dedent(
                f"""#!/bin/bash
                set -euo pipefail
                if [ "${{1:-}}" = "start-server" ]; then exit 0; fi
                if [ "${{1:-}}" = "devices" ]; then
                  printf 'List of devices attached\nwatch-a\tdevice\n'
                  exit 0
                fi
                if [ "${{1:-}}" = "-s" ]; then
                  serial="$2"
                  shift 2
                  [ "$serial" = "watch-a" ] || exit 90
                  if [ "${{1:-}}" = "exec-out" ]; then
                    shift
                    if [ "$*" = "cat /data/app/raiseai/base.apk" ]; then
                      printf 'synthetic-installed-raise-ai-apk'
                      exit 0
                    fi
                  fi
                  if [ "${{1:-}}" = "shell" ]; then
                    shift
                    case "$*" in
                      "getprop ro.product.model") echo "SM_L315F" ;;
                      "getprop ro.build.characteristics") echo "watch" ;;
                      "pm list features") echo "feature:android.hardware.type.watch" ;;
                      "dumpsys package nl.zennay.raiseai")
                        printf '  versionCode=152\n  versionName=1.5.2\n'
                        ;;
                      "pm path nl.zennay.raiseai")
                        echo "package:/data/app/raiseai/base.apk"
                        ;;
                      "date +%z")
                        echo "+0100"
                        ;;
                      "dumpsys activity services nl.zennay.raiseai")
                        echo "{service_line}"
                        ;;
                      "dumpsys activity exit-info nl.zennay.raiseai")
                        cat <<'EOF_EXIT'
ACTIVITY MANAGER PROCESS EXIT INFO (dumpsys activity exit-info)
Last Timestamp of Persistence Into Persistent Storage: 2026-10-05 06:00:00.000
  package: nl.zennay.raiseai
    Historical Process Exit for uid=10123
        ApplicationExitInfo #0:
          timestamp=2026-10-05 06:15:00.000
          pid=1234
          realUid=10123
          packageUid=10123
          definingUid=10123
          user=0
          process=nl.zennay.raiseai
          reason={reason} ({reason_label})
          status={status}
          importance=100
          pss=0.00
          rss=0.00
          description=null
          state=empty
          trace=null
EOF_EXIT
                        ;;
                      *) echo "unexpected shell invocation: $*" >&2; exit 91 ;;
                    esac
                    exit 0
                  fi
                fi
                echo "unexpected adb invocation: $*" >&2
                exit 92
                """
            ).lstrip(),
            encoding="utf-8",
        )
        self.adb.chmod(0o755)

    def run_snapshot(self, label):
        env = os.environ.copy()
        env["PATH"] = f"{self.bin}:{env['PATH']}"
        env["HOME"] = str(self.root / "home")
        return subprocess.run(
            [
                "bash",
                str(self.repo / "watch-stability-snapshot.command"),
                label,
                str(self.session),
            ],
            cwd=self.repo,
            env=env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )

    def test_clean_exit_history_produces_bound_stability_pass(self):
        result = self.run_snapshot("clean")
        self.assertEqual(result.returncode, 0, result.stdout)

        summary = json.loads(
            (self.session / "stability-clean.json").read_text(encoding="utf-8")
        )
        self.assertTrue(summary["stability_valid"])
        self.assertEqual(summary["watch_serial"], "watch-a")
        self.assertEqual(summary["source_revision"], REVISION)
        self.assertEqual(summary["installed_apk_sha256"], APK_SHA)
        self.assertTrue(summary["gesture_monitor_service_running"])
        self.assertEqual(summary["critical_exit_count"], 0)

    def test_anr_is_preserved_as_machine_readable_failure(self):
        self._write_adb(reason=6, reason_label="ANR", status=0, service=True)
        result = self.run_snapshot("anr")
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("STABILITY FAIL", result.stdout)

        summary = json.loads(
            (self.session / "stability-anr.json").read_text(encoding="utf-8")
        )
        self.assertFalse(summary["stability_valid"])
        self.assertEqual(summary["critical_reasons"], ["REASON_ANR"])

    def test_inactive_gesture_service_fails_without_inventing_crash(self):
        self._write_adb(
            reason=10,
            reason_label="USER REQUESTED",
            status=0,
            service=False,
        )
        result = self.run_snapshot("service-down")
        self.assertEqual(result.returncode, 1, result.stdout)

        summary = json.loads(
            (self.session / "stability-service-down.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertFalse(summary["stability_valid"])
        self.assertEqual(summary["critical_exit_count"], 0)
        self.assertFalse(summary["gesture_monitor_service_running"])


if __name__ == "__main__":
    unittest.main()
