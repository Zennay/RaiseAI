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


class InstallWatchBindingTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.bin = self.root / "bin"
        self.bin.mkdir()
        self.sdk = self.root / "sdk"
        (self.sdk / "platform-tools").mkdir(parents=True)
        self.log = self.root / "adb-install.log"
        self.serial_file = self.root / "installed-watch-serial"
        self.apk = self.root / "RaiseAI.apk"
        self.apk.write_bytes(b"synthetic-watch-apk")

        adb = self.sdk / "platform-tools" / "adb"
        adb.write_text(
            textwrap.dedent(
                r"""#!/bin/bash
set -eu
if [ "${1:-}" = "start-server" ]; then
  exit 0
fi
if [ "${1:-}" = "devices" ]; then
  printf 'List of devices attached\nphone-a\tdevice\nwatch-b\tdevice\n'
  exit 0
fi
if [ "${1:-}" = "mdns" ]; then
  exit 0
fi
if [ "${1:-}" = "-s" ]; then
  serial="$2"
  printf '%s\n' "$serial" >> "$ADB_LOG"
  shift 2
  args="$*"
  case "$args" in
    "shell getprop ro.product.model")
      [ "$serial" = "watch-b" ] && echo "SM_L315F" || echo "Pixel_Test"
      ;;
    "shell getprop ro.product.device")
      [ "$serial" = "watch-b" ] && echo "freshbl" || echo "phone"
      ;;
    "shell getprop ro.build.characteristics")
      [ "$serial" = "watch-b" ] && echo "watch" || echo "nosdcard"
      ;;
    "shell pm list features")
      if [ "$serial" = "watch-b" ]; then
        echo "feature:android.hardware.type.watch"
      else
        echo "feature:android.hardware.telephony"
      fi
      ;;
    "shell getprop ro.product.cpu.abi")
      echo "armeabi-v7a"
      ;;
    "shell getprop ro.product.cpu.abilist")
      echo "armeabi-v7a"
      ;;
    install\ --no-streaming\ -r\ *)
      echo "Success"
      ;;
    "shell appops set nl.zennay.raiseai SYSTEM_ALERT_WINDOW allow"|"shell appops set nl.zennay.raiseai GET_USAGE_STATS allow")
      ;;
    "shell am start -n nl.zennay.raiseai/.MainActivity")
      ;;
    "shell dumpsys package nl.zennay.raiseai")
      printf '  versionCode=152\n  versionName=1.5.2\n'
      ;;
    *)
      echo "unexpected adb invocation: $serial $args" >&2
      exit 2
      ;;
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

        unzip = self.bin / "unzip"
        unzip.write_text(
            "#!/bin/bash\nprintf 'lib/armeabi-v7a/libraiseai.so\\n'\n",
            encoding="utf-8",
        )
        unzip.chmod(0o755)

    def tearDown(self):
        self.temp.cleanup()

    def run_installer(self, serial):
        env = os.environ.copy()
        env["ANDROID_SDK_ROOT"] = str(self.sdk)
        env["ANDROID_SERIAL"] = serial
        env["ADB_LOG"] = str(self.log)
        env["RAISE_INSTALLED_WATCH_SERIAL_FILE"] = str(self.serial_file)
        env["PATH"] = f"{self.bin}:{env['PATH']}"
        return subprocess.run(
            ["bash", str(ROOT / "install-watch-apk.command"), str(self.apk)],
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

    def test_installer_attests_exact_selected_watch(self):
        result = self.run_installer("watch-b")
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertEqual(self.serial_file.read_text(encoding="utf-8").strip(), "watch-b")
        self.assertTrue(self.used_serials())
        self.assertEqual(set(self.used_serials()), {"watch-b"})

    def test_installer_rejects_non_watch_android_serial(self):
        result = self.run_installer("phone-a")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Selected ADB target is not a Wear OS watch", result.stdout)
        self.assertFalse(self.serial_file.exists())


if __name__ == "__main__":
    unittest.main()
