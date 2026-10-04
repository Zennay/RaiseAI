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
  if [ "${SWITCH_AFTER_FAILED_INSTALL:-}" = "1" ] && [ -f "${INSTALL_ATTEMPT_FILE:-}" ]; then
    printf 'List of devices attached\nphone-a\tdevice\nwatch-c\tdevice\n'
  else
    printf 'List of devices attached\nphone-a\tdevice\nwatch-b\tdevice\n'
  fi
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
      if [ "${MUTATE_BOUND_TARGET_AFTER_FAILED_INSTALL:-}" = "1" ] &&
         [ -f "${INSTALL_ATTEMPT_FILE:-}" ] &&
         [ "$serial" = "watch-b" ]; then
        echo "Pixel_Test"
      elif [ "$serial" = "watch-b" ] || [ "$serial" = "watch-c" ]; then
        echo "SM_L315F"
      else
        echo "Pixel_Test"
      fi
      ;;
    "shell getprop ro.product.device")
      if [ "${MUTATE_BOUND_TARGET_AFTER_FAILED_INSTALL:-}" = "1" ] &&
         [ -f "${INSTALL_ATTEMPT_FILE:-}" ] &&
         [ "$serial" = "watch-b" ]; then
        echo "phone"
      else
        [ "$serial" = "watch-b" ] && echo "freshbl" || echo "phone"
      fi
      ;;
    "shell getprop ro.build.characteristics")
      if [ "${MUTATE_BOUND_TARGET_AFTER_FAILED_INSTALL:-}" = "1" ] &&
         [ -f "${INSTALL_ATTEMPT_FILE:-}" ] &&
         [ "$serial" = "watch-b" ]; then
        echo "nosdcard"
      else
        [ "$serial" = "watch-b" ] && echo "watch" || echo "nosdcard"
      fi
      ;;
    "shell pm list features")
      if [ "${MUTATE_BOUND_TARGET_AFTER_FAILED_INSTALL:-}" = "1" ] &&
         [ -f "${INSTALL_ATTEMPT_FILE:-}" ] &&
         [ "$serial" = "watch-b" ]; then
        echo "feature:android.hardware.telephony"
      elif [ "$serial" = "watch-b" ]; then
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
      if [ "${FAIL_FIRST_INSTALL:-}" = "1" ] && [ ! -f "${INSTALL_ATTEMPT_FILE:-}" ]; then
        : > "$INSTALL_ATTEMPT_FILE"
        echo "error: device disconnected" >&2
        exit 1
      fi
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

    def run_installer(self, serial=None, extra_env=None):
        env = os.environ.copy()
        env["ANDROID_SDK_ROOT"] = str(self.sdk)
        if serial is None:
            env.pop("ANDROID_SERIAL", None)
        else:
            env["ANDROID_SERIAL"] = serial
        if extra_env:
            env.update(extra_env)
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

    def test_install_retry_refuses_to_switch_to_another_watch(self):
        attempt_file = self.root / "install-attempted"
        result = self.run_installer(
            None,
            {
                "FAIL_FIRST_INSTALL": "1",
                "SWITCH_AFTER_FAILED_INSTALL": "1",
                "INSTALL_ATTEMPT_FILE": str(attempt_file),
            },
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Bound Watch did not reconnect: watch-b", result.stdout)
        self.assertIn("Refusing to select a different ADB device", result.stdout)
        self.assertFalse(self.serial_file.exists())
        self.assertNotIn("watch-c", self.used_serials())

    def test_install_retry_revalidates_bound_watch_identity(self):
        attempt_file = self.root / "install-attempted"
        result = self.run_installer(
            "watch-b",
            {
                "FAIL_FIRST_INSTALL": "1",
                "MUTATE_BOUND_TARGET_AFTER_FAILED_INSTALL": "1",
                "INSTALL_ATTEMPT_FILE": str(attempt_file),
            },
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn(
            "Bound ADB target no longer identifies as a Wear OS watch: watch-b",
            result.stdout,
        )
        self.assertIn(
            "Refusing the install retry to preserve physical evidence provenance.",
            result.stdout,
        )
        self.assertFalse(self.serial_file.exists())


class GatewayProvisionBindingTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.sdk = self.root / "sdk"
        (self.sdk / "platform-tools").mkdir(parents=True)
        self.log = self.root / "adb-provision.log"
        self.profile = self.root / "watch-gateway.properties"
        self.profile.write_text(
            "url=https://raise.example.invalid:8787\\n"
            "token=abcdefghijklmnopqrstuvwxyz0123456789TOKEN\\n"
            "spki_sha256=" + ("a" * 64) + "\\n",
            encoding="utf-8",
        )

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
    "shell run-as nl.zennay.raiseai id")
      exit 0
      ;;
    push\ *)
      exit 0
      ;;
    shell\ chmod\ 600\ /data/local/tmp/raise-gateway-*.properties)
      exit 0
      ;;
    shell\ run-as\ nl.zennay.raiseai\ sh\ -c\ *)
      exit 0
      ;;
    shell\ rm\ -f\ /data/local/tmp/raise-gateway-*.properties)
      exit 0
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

    def tearDown(self):
        self.temp.cleanup()

    def run_provisioner(self, serial):
        env = os.environ.copy()
        env["ANDROID_SDK_ROOT"] = str(self.sdk)
        env["ANDROID_SERIAL"] = serial
        env["ADB_LOG"] = str(self.log)
        return subprocess.run(
            ["bash", str(ROOT / "provision-watch-gateway.command"), str(self.profile)],
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

    def test_gateway_provisioning_stays_on_bound_watch(self):
        result = self.run_provisioner("watch-b")
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertTrue(self.used_serials())
        self.assertEqual(set(self.used_serials()), {"watch-b"})
        self.assertIn("Gateway profile installed on Watch: watch-b", result.stdout)

    def test_gateway_provisioning_rejects_bound_phone(self):
        result = self.run_provisioner("phone-a")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Refusing gateway provisioning to non-Wear ADB target: phone-a", result.stdout)
        self.assertEqual(set(self.used_serials()), {"phone-a"})

class PhysicalPrepareBindingTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.repo = self.root / "repo"
        self.repo.mkdir()
        self.bin = self.root / "bin"
        self.bin.mkdir()
        self.evidence = self.root / "evidence"
        self.profile = self.root / "watch-gateway.properties"
        self.profile.write_text("synthetic=true\n", encoding="utf-8")
        self.apk = self.root / "RaiseAI-v1.5.2-debug.apk"
        self.apk.write_bytes(b"physical-prepare-binding-apk")

        shutil.copy2(ROOT / "physical-validation.command", self.repo / "physical-validation.command")
        (self.repo / "VERSION.txt").write_text("1.5.2\n", encoding="utf-8")
        (self.repo / "app").mkdir()
        (self.repo / "app" / "build.gradle.kts").write_text(
            'android { defaultConfig { versionName = "1.5.2" } }\n',
            encoding="utf-8",
        )
        (self.repo / "tools").mkdir()
        (self.repo / "tools" / "verify-watch-apk-identity.py").write_text(
            "import json\nprint(json.dumps({'ok': True}))\n",
            encoding="utf-8",
        )

        installer = self.repo / "install-watch-apk.command"
        installer.write_text(
            """#!/bin/bash
set -euo pipefail
: "${RAISE_INSTALLED_WATCH_SERIAL_FILE:?missing install serial output}"
printf 'watch-b\\n' > "$RAISE_INSTALLED_WATCH_SERIAL_FILE"
""",
            encoding="utf-8",
        )
        installer.chmod(0o755)

        provision = self.repo / "provision-watch-gateway.command"
        provision.write_text(
            """#!/bin/bash
set -euo pipefail
[ "${ANDROID_SERIAL:-}" = "watch-b" ] || {
  echo "provision received wrong serial: ${ANDROID_SERIAL:-<unset>}"
  exit 42
}
printf '%s\\n' "$ANDROID_SERIAL" > "$PROVISION_SERIAL_LOG"
""",
            encoding="utf-8",
        )
        provision.chmod(0o755)

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
  shift 2
  args="$*"
  case "$args" in
    "shell getprop ro.product.model") echo "SM_L315F" ;;
    "shell getprop ro.build.characteristics") echo "watch" ;;
    "shell pm list features") echo "feature:android.hardware.type.watch" ;;
    "shell dumpsys package nl.zennay.raiseai")
      printf '  versionName=1.5.2\n'
      ;;
    "shell run-as nl.zennay.raiseai sh -c 'rm -f files/watch-e2e-evidence.json files/sensor-traces.csv files/sensor-trials.csv'")
      ;;
    "logcat -c")
      ;;
    "shell am start -n nl.zennay.raiseai/.MainActivity")
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

        subprocess.run(["git", "init", "-q", self.repo], check=True)
        subprocess.run(
            ["git", "-C", self.repo, "config", "user.email", "raiseai-ci@example.invalid"],
            check=True,
        )
        subprocess.run(
            ["git", "-C", self.repo, "config", "user.name", "RaiseAI CI"],
            check=True,
        )
        subprocess.run(["git", "-C", self.repo, "add", "."], check=True)
        subprocess.run(["git", "-C", self.repo, "commit", "-qm", "fixture"], check=True)

    def tearDown(self):
        self.temp.cleanup()

    def test_prepare_uses_installer_attested_watch_for_provision_and_session(self):
        provision_log = self.root / "provision-serial"
        env = os.environ.copy()
        env["PATH"] = f"{self.bin}:{env['PATH']}"
        env["RAISE_EVIDENCE_ROOT"] = str(self.evidence)
        env["RAISE_PREBUILT_APK"] = str(self.apk)
        env["RAISE_EXPECT_APK_SHA256"] = hashlib.sha256(self.apk.read_bytes()).hexdigest()
        env["PROVISION_SERIAL_LOG"] = str(provision_log)
        env.pop("ANDROID_SERIAL", None)

        result = subprocess.run(
            ["bash", str(self.repo / "physical-validation.command"), "prepare", str(self.profile)],
            cwd=self.repo,
            env=env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )

        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertEqual(provision_log.read_text(encoding="utf-8").strip(), "watch-b")
        sessions = [path for path in self.evidence.iterdir() if path.is_dir()]
        self.assertEqual(len(sessions), 1)
        payload = json.loads((sessions[0] / "session.json").read_text(encoding="utf-8"))
        self.assertEqual(payload["watch_serial"], "watch-b")


if __name__ == "__main__":
    unittest.main()
