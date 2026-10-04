import os
import subprocess
import tempfile
import textwrap
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class AdbDeviceBindingTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.bin = self.root / "bin"
        self.bin.mkdir()
        self.log = self.root / "adb.log"

        adb = self.bin / "adb"
        adb.write_text(
            textwrap.dedent(
                r"""#!/bin/bash
set -eu
if [ "${1:-}" = "devices" ]; then
  printf 'List of devices attached\nwatch-a\tdevice\nwatch-b\tdevice\n'
  exit 0
fi
if [ "${1:-}" = "-s" ]; then
  serial="$2"
  printf '%s\n' "$serial" >> "$ADB_LOG"
  shift 2
  args="$*"
  case "$args" in
    *"getprop ro.product.model"*) echo "SM_L315F" ;;
    *"getprop ro.build.characteristics"*) echo "watch" ;;
    *"pm list features"*) echo "feature:android.hardware.type.watch" ;;
    *"cat files/watch-e2e-evidence.json"*) exit 1 ;;
    *"cat files/sensor-traces.csv"*) echo "timestamp_ns,label,ax,ay,az" ;;
    *"cat files/sensor-trials.csv"*) echo "trial_id,label,detected" ;;
    *) echo "ok" ;;
  esac
  exit 0
fi
echo "unexpected adb invocation: $*" >&2
exit 2
"""
            ),
            encoding="utf-8",
        )
        adb.chmod(0o755)

        python = self.bin / "python3"
        python.write_text("#!/bin/bash\nexit 0\n", encoding="utf-8")
        python.chmod(0o755)

    def tearDown(self):
        self.temp.cleanup()

    def run_script(self, script_name, serial):
        env = os.environ.copy()
        env["PATH"] = f"{self.bin}:{env['PATH']}"
        env["ANDROID_SERIAL"] = serial
        env["ADB_LOG"] = str(self.log)
        env["RAISE_OUTPUT_DIR"] = str(self.root / "out")
        return subprocess.run(
            ["bash", str(ROOT / script_name)],
            cwd=ROOT,
            env=env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )

    def used_serials(self):
        if not self.log.exists():
            return []
        return [
            line.strip()
            for line in self.log.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]

    def test_pull_diagnostics_uses_bound_android_serial(self):
        result = self.run_script("pull-diagnostics.command", "watch-b")
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertTrue(self.used_serials())
        self.assertEqual(set(self.used_serials()), {"watch-b"})

    def test_pull_watch_data_uses_bound_android_serial(self):
        result = self.run_script("pull-watch-data.command", "watch-b")
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertTrue(self.used_serials())
        self.assertEqual(set(self.used_serials()), {"watch-b"})

    def test_disconnected_bound_serial_fails_closed(self):
        for script_name in ("pull-diagnostics.command", "pull-watch-data.command"):
            self.log.write_text("", encoding="utf-8")
            result = self.run_script(script_name, "watch-missing")
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("Prepared Watch is not connected over ADB", result.stdout)
            self.assertEqual(self.used_serials(), [])


if __name__ == "__main__":
    unittest.main()
