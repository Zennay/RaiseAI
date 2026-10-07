import os
import signal
import shutil
import subprocess
import tempfile
import textwrap
import time
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class FrozenAcceptanceLauncherTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.repo = self.root / "repo"
        self.repo.mkdir()
        self.bin = self.root / "bin"
        self.bin.mkdir()
        self.log = self.root / "handoff.log"
        self.fetch_marker = self.root / "fetch-called"
        self.profile = self.root / "watch-gateway.properties"
        self.profile.write_text(
            "url=https://raise.example.invalid\n"
            "token=" + ("x" * 40) + "\n"
            "spki_sha256=" + ("a" * 64) + "\n",
            encoding="utf-8",
        )

        shutil.copy2(
            ROOT / "start-frozen-acceptance.command",
            self.repo / "start-frozen-acceptance.command",
        )
        tools = self.repo / "tools"
        tools.mkdir()
        (tools / "fetch-frozen-physical-handoff.py").write_text(
            textwrap.dedent(
                r"""
                import argparse
                import os
                from pathlib import Path

                parser = argparse.ArgumentParser()
                parser.add_argument("--output", required=True)
                args = parser.parse_args()
                output = Path(args.output)
                output.mkdir(parents=True)
                marker = os.environ.get("FAKE_FETCH_MARKER")
                if marker:
                    Path(marker).write_text("called\n", encoding="utf-8")
                mutate_profile = os.environ.get("FAKE_MUTATE_PROFILE")
                if mutate_profile:
                    Path(mutate_profile).write_text(
                        "url=https://attacker.invalid\n"
                        "token=changed-after-snapshot\n"
                        "spki_sha256=" + ("b" * 64) + "\n",
                        encoding="utf-8",
                    )

                launcher = output / "start-physical-handoff.command"
                launcher.write_text(
                    r'''#!/bin/bash
                set -euo pipefail
                : "${FAKE_HANDOFF_LOG:?}"
                if [ "${1:-}" = "--verify-only" ]; then
                  if [ "${FAKE_VERIFY_FAIL:-0}" = "1" ]; then
                    echo "simulated frozen handoff verification failure"
                    exit 70
                  fi
                  [ -n "${RAISE_RESTORE_DIR:-}" ] || {
                    echo "verify restore directory missing"
                    exit 71
                  }
                  mkdir -p "$RAISE_RESTORE_DIR"
                  printf 'verify:%s\n' "$RAISE_RESTORE_DIR" >> "$FAKE_HANDOFF_LOG"
                  echo "VERIFY-ONLY PASS"
                  exit 0
                fi

                [ "${ANDROID_SERIAL:-}" = "watch-1" ] || {
                  echo "wrong bound serial: ${ANDROID_SERIAL:-<unset>}"
                  exit 72
                }
                [ -x "${ANDROID_SDK_ROOT:-}/platform-tools/adb" ] || {
                  echo "shim adb missing"
                  exit 73
                }
                [ -d "${ANDROID_SDK_ROOT:-}/build-tools" ] || {
                  echo "shim build-tools directory missing"
                  exit 74
                }
                if find "$ANDROID_SDK_ROOT/build-tools" -type f | grep -q .; then
                  echo "build-tools shim unexpectedly contains files"
                  exit 75
                fi
                [ -n "${RAISE_RESTORE_DIR:-}" ] || {
                  echo "run restore directory missing"
                  exit 76
                }
                case "$RAISE_RESTORE_DIR" in
                  *verify-source*)
                    echo "real run reused verify source"
                    exit 77
                    ;;
                esac
                [ -f "${1:-}" ] || {
                  echo "gateway profile snapshot missing"
                  exit 78
                }
                grep -q '^url=https://raise.example.invalid$' "$1" || {
                  echo "gateway profile snapshot changed"
                  exit 79
                }
                grep -q '^token=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx$' "$1" || {
                  echo "gateway profile snapshot token changed"
                  exit 80
                }
                printf 'run:%s:%s:%s:%s\n' \
                  "$ANDROID_SERIAL" "$ANDROID_SDK_ROOT" "$RAISE_RESTORE_DIR" "$1" \
                  >> "$FAKE_HANDOFF_LOG"
                ''',
                    encoding="utf-8",
                )
                """
            ).lstrip(),
            encoding="utf-8",
        )

        adb = self.bin / "adb"
        adb.write_text(
            textwrap.dedent(
                r"""#!/bin/bash
                set -eu
                if [ "${1:-}" = "start-server" ]; then
                  if [ -n "${FAKE_ADB_START_MARKER:-}" ]; then
                    printf 'started\n' > "$FAKE_ADB_START_MARKER"
                  fi
                  if [ "${FAKE_ADB_START_DELAY:-0}" != "0" ]; then
                    sleep "$FAKE_ADB_START_DELAY"
                  fi
                  exit 0
                fi
                if [ "${1:-}" = "devices" ]; then
                  printf 'List of devices attached\n'
                  if [ "${FAKE_NO_DEVICES:-0}" = "1" ]; then
                    :
                  elif [ "${FAKE_MULTIPLE_DEVICES:-0}" = "1" ]; then
                    printf 'watch-1\tdevice\nphone-1\tdevice\n'
                  else
                    printf 'watch-1\tdevice\n'
                  fi
                  exit 0
                fi
                if [ "${1:-}" = "-s" ]; then
                  serial="$2"
                  shift 2
                  [ "$serial" = "watch-1" ] || exit 90
                  case "$*" in
                    "shell getprop ro.product.model")
                      printf '%s\n' "${FAKE_MODEL:-SM-L315F}"
                      ;;
                    "shell getprop ro.build.characteristics")
                      if [ "${FAKE_NOT_WEAR:-0}" = "1" ]; then
                        echo "nosdcard"
                      else
                        echo "watch"
                      fi
                      ;;
                    "shell pm list features")
                      if [ "${FAKE_NOT_WEAR:-0}" != "1" ]; then
                        echo "feature:android.hardware.type.watch"
                      fi
                      ;;
                    *)
                      echo "unexpected adb invocation: $*" >&2
                      exit 91
                      ;;
                  esac
                  exit 0
                fi
                echo "unexpected adb invocation: $*" >&2
                exit 92
                """
            ).lstrip(),
            encoding="utf-8",
        )
        adb.chmod(0o755)

    def tearDown(self):
        self.temp.cleanup()

    def run_launcher(self, extra_env=None, args=None):
        env = os.environ.copy()
        env.pop("ANDROID_SDK_ROOT", None)
        env.pop("ANDROID_HOME", None)
        env["PATH"] = f"{self.bin}:{env['PATH']}"
        env["FAKE_HANDOFF_LOG"] = str(self.log)
        env["FAKE_FETCH_MARKER"] = str(self.fetch_marker)
        if extra_env:
            env.update(extra_env)
        command = [
            "bash",
            str(self.repo / "start-frozen-acceptance.command"),
        ]
        if args is None:
            command.append(str(self.profile))
        else:
            command.extend(args)
        return subprocess.run(
            command,
            cwd=self.repo,
            env=env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )

    def test_runs_verified_handoff_bound_to_single_galaxy_watch(self):
        result = self.run_launcher()

        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertTrue(self.fetch_marker.exists())
        lines = self.log.read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(lines), 2)
        self.assertTrue(lines[0].startswith("verify:"))
        self.assertTrue(lines[1].startswith("run:watch-1:"))
        passed_profile = lines[1].rsplit(":", 1)[1]
        self.assertNotEqual(passed_profile, str(self.profile.resolve()))
        self.assertTrue(passed_profile.endswith("/watch-gateway.properties"))

    def test_snapshots_gateway_profile_before_fetch_side_effects(self):
        result = self.run_launcher(
            {"FAKE_MUTATE_PROFILE": str(self.profile)}
        )

        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("attacker.invalid", self.profile.read_text(encoding="utf-8"))
        lines = self.log.read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(lines), 2)
        self.assertTrue(lines[1].startswith("run:watch-1:"))

    def test_rejects_malformed_gateway_profiles_before_adb_or_fetch(self):
        cases = {
            "http-url": (
                "url=http://raise.example.invalid\n"
                "token=" + ("x" * 40) + "\n"
                "spki_sha256=" + ("a" * 64) + "\n",
                "expected HTTPS origin",
            ),
            "short-token": (
                "url=https://raise.example.invalid\n"
                "token=short\n"
                "spki_sha256=" + ("a" * 64) + "\n",
                "token is missing or malformed",
            ),
            "bad-pin": (
                "url=https://raise.example.invalid\n"
                "token=" + ("x" * 40) + "\n"
                "spki_sha256=not-a-pin\n",
                "SPKI pin must be 64 hex characters",
            ),
            "duplicate-token": (
                "url=https://raise.example.invalid\n"
                "token=" + ("x" * 40) + "\n"
                "token=" + ("y" * 40) + "\n"
                "spki_sha256=" + ("a" * 64) + "\n",
                "duplicate token property",
            ),
            "unexpected-property": (
                "url=https://raise.example.invalid\n"
                "token=" + ("x" * 40) + "\n"
                "spki_sha256=" + ("a" * 64) + "\n"
                "future_mode=enabled\n",
                "unexpected property: future_mode",
            ),
            "spaced-key": (
                " url=https://raise.example.invalid\n"
                "token=" + ("x" * 40) + "\n"
                "spki_sha256=" + ("a" * 64) + "\n",
                "url property must use canonical key=value syntax",
            ),
            "spaced-value": (
                "url=https://raise.example.invalid \n"
                "token=" + ("x" * 40) + "\n"
                "spki_sha256=" + ("a" * 64) + "\n",
                "url property must use canonical key=value syntax",
            ),
        }

        for name, (payload, expected_error) in cases.items():
            with self.subTest(name=name):
                profile = self.root / f"{name}.properties"
                profile.write_text(payload, encoding="utf-8")
                adb_started = self.root / f"{name}-adb-started"
                result = self.run_launcher(
                    {"FAKE_ADB_START_MARKER": str(adb_started)},
                    args=[str(profile)],
                )

                self.assertNotEqual(result.returncode, 0, result.stdout)
                self.assertIn(expected_error, result.stdout)
                self.assertFalse(adb_started.exists(), result.stdout)
                self.assertFalse(self.fetch_marker.exists(), result.stdout)
                self.assertFalse(self.log.exists(), result.stdout)

    def test_rejects_symlink_gateway_profile_before_fetch(self):
        linked_profile = self.root / "linked-watch-gateway.properties"
        linked_profile.symlink_to(self.profile)

        result = self.run_launcher(args=[str(linked_profile)])

        self.assertNotEqual(result.returncode, 0)
        self.assertIn(
            "Gateway profile must be a regular non-symlink file",
            result.stdout,
        )
        self.assertFalse(self.fetch_marker.exists())
        self.assertFalse(self.log.exists())

    def test_rejects_fifo_gateway_profile_before_fetch(self):
        fifo_profile = self.root / "fifo-watch-gateway.properties"
        os.mkfifo(fifo_profile)

        result = self.run_launcher(args=[str(fifo_profile)])

        self.assertNotEqual(result.returncode, 0)
        self.assertIn(
            "Gateway profile must be a regular non-symlink file",
            result.stdout,
        )
        self.assertFalse(self.fetch_marker.exists())
        self.assertFalse(self.log.exists())

    def _assert_signal_exits_before_post_signal_side_effects(
        self,
        signal_number: int,
        expected_returncode: int,
    ):
        adb_started = self.root / "adb-started"
        env = os.environ.copy()
        env.pop("ANDROID_SDK_ROOT", None)
        env.pop("ANDROID_HOME", None)
        env["PATH"] = f"{self.bin}:{env['PATH']}"
        env["FAKE_HANDOFF_LOG"] = str(self.log)
        env["FAKE_FETCH_MARKER"] = str(self.fetch_marker)
        env["FAKE_ADB_START_MARKER"] = str(adb_started)
        env["FAKE_ADB_START_DELAY"] = "0.4"

        process = subprocess.Popen(
            [
                "bash",
                str(self.repo / "start-frozen-acceptance.command"),
                str(self.profile),
            ],
            cwd=self.repo,
            env=env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )
        deadline = time.monotonic() + 2.0
        while not adb_started.exists() and process.poll() is None:
            if time.monotonic() >= deadline:
                process.kill()
                self.fail("launcher did not reach the fake adb start-server boundary")
            time.sleep(0.01)

        process.send_signal(signal_number)
        stdout, _ = process.communicate(timeout=3)

        self.assertEqual(process.returncode, expected_returncode, stdout)
        self.assertFalse(self.fetch_marker.exists(), stdout)
        self.assertFalse(self.log.exists(), stdout)

    def test_term_exits_before_post_signal_fetch_side_effects(self):
        self._assert_signal_exits_before_post_signal_side_effects(
            signal.SIGTERM,
            143,
        )

    def test_int_exits_before_post_signal_fetch_side_effects(self):
        self._assert_signal_exits_before_post_signal_side_effects(
            signal.SIGINT,
            130,
        )

    def test_preflight_only_verifies_handoff_without_starting_session(self):
        result = self.run_launcher(
            args=["--preflight-only", str(self.profile)]
        )

        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertTrue(self.fetch_marker.exists())
        lines = self.log.read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(lines), 1)
        self.assertTrue(lines[0].startswith("verify:"))
        self.assertIn("FROZEN-ACCEPTANCE PREFLIGHT PASS", result.stdout)
        self.assertIn(
            "No APK was installed and no physical acceptance session was started.",
            result.stdout,
        )

    def test_preflight_rejects_extra_arguments_before_side_effects(self):
        result = self.run_launcher(
            args=["--preflight-only", str(self.profile), "unexpected-extra"]
        )

        self.assertEqual(result.returncode, 2, result.stdout)
        self.assertIn("Usage:", result.stdout)
        self.assertFalse(self.fetch_marker.exists())
        self.assertFalse(self.log.exists())

    def test_run_mode_rejects_extra_arguments_before_side_effects(self):
        result = self.run_launcher(args=[str(self.profile), "unexpected-extra"])

        self.assertEqual(result.returncode, 2, result.stdout)
        self.assertIn("Usage:", result.stdout)
        self.assertFalse(self.fetch_marker.exists())
        self.assertFalse(self.log.exists())

    def test_help_exits_without_profile_device_or_fetch_side_effects(self):
        missing_profile = self.root / "missing.properties"
        result = self.run_launcher(
            {"FAKE_NO_DEVICES": "1"},
            args=["--help", str(missing_profile)],
        )

        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("Usage:", result.stdout)
        self.assertFalse(self.fetch_marker.exists())
        self.assertFalse(self.log.exists())

    def test_explicit_sdk_adb_wins_over_path_adb(self):
        sdk_root = self.root / "explicit-sdk"
        sdk_adb = sdk_root / "platform-tools" / "adb"
        sdk_adb.parent.mkdir(parents=True)
        shutil.copy2(self.bin / "adb", sdk_adb)
        sdk_adb.chmod(0o755)

        bad_adb_marker = self.root / "path-adb-used"
        (self.bin / "adb").write_text(
            "#!/bin/bash\n"
            "printf 'used\\n' > \"$BAD_ADB_MARKER\"\n"
            "exit 99\n",
            encoding="utf-8",
        )
        (self.bin / "adb").chmod(0o755)

        result = self.run_launcher(
            {
                "ANDROID_SDK_ROOT": str(sdk_root),
                "BAD_ADB_MARKER": str(bad_adb_marker),
            },
            args=["--preflight-only", str(self.profile)],
        )

        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertFalse(bad_adb_marker.exists(), result.stdout)
        self.assertTrue(self.fetch_marker.exists())
        lines = self.log.read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(lines), 1)
        self.assertTrue(lines[0].startswith("verify:"))

    def test_rejects_no_active_adb_device_before_fetch(self):
        result = self.run_launcher({"FAKE_NO_DEVICES": "1"})

        self.assertNotEqual(result.returncode, 0)
        self.assertIn(
            "Frozen acceptance requires exactly one active ADB device; found 0.",
            result.stdout,
        )
        self.assertFalse(self.fetch_marker.exists())
        self.assertFalse(self.log.exists())

    def test_unknown_option_fails_before_fetch(self):
        result = self.run_launcher(args=["--definitely-not-a-real-option"])

        self.assertEqual(result.returncode, 2, result.stdout)
        self.assertIn("Unknown option: --definitely-not-a-real-option", result.stdout)
        self.assertIn("Usage:", result.stdout)
        self.assertFalse(self.fetch_marker.exists())
        self.assertFalse(self.log.exists())

    def test_preflight_stops_when_frozen_handoff_verification_fails(self):
        result = self.run_launcher(
            {"FAKE_VERIFY_FAIL": "1"},
            args=["--preflight-only", str(self.profile)],
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertTrue(self.fetch_marker.exists())
        self.assertIn(
            "simulated frozen handoff verification failure",
            result.stdout,
        )
        self.assertNotIn("FROZEN-ACCEPTANCE PREFLIGHT PASS", result.stdout)
        self.assertFalse(self.log.exists())

    def test_rejects_matching_model_that_is_not_wear_os_before_fetch(self):
        result = self.run_launcher({"FAKE_NOT_WEAR": "1"})

        self.assertNotEqual(result.returncode, 0)
        self.assertIn(
            "Selected ADB target does not identify as Wear OS",
            result.stdout,
        )
        self.assertFalse(self.fetch_marker.exists())
        self.assertFalse(self.log.exists())

    def test_rejects_multiple_active_adb_devices_before_fetch(self):
        result = self.run_launcher({"FAKE_MULTIPLE_DEVICES": "1"})

        self.assertNotEqual(result.returncode, 0)
        self.assertIn(
            "Frozen acceptance requires exactly one active ADB device; found 2.",
            result.stdout,
        )
        self.assertFalse(self.fetch_marker.exists())
        self.assertFalse(self.log.exists())

    def test_rejects_unexpected_watch_model_before_fetch(self):
        result = self.run_launcher({"FAKE_MODEL": "Pixel Watch 3"})

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Refusing frozen acceptance on unexpected Watch model", result.stdout)
        self.assertFalse(self.fetch_marker.exists())
        self.assertFalse(self.log.exists())


if __name__ == "__main__":
    unittest.main()
