import os
import shutil
import subprocess
import tempfile
import textwrap
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

                launcher = output / "start-physical-handoff.command"
                launcher.write_text(
                    r'''#!/bin/bash
                set -euo pipefail
                : "${FAKE_HANDOFF_LOG:?}"
                if [ "${1:-}" = "--verify-only" ]; then
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
                  echo "absolute gateway profile missing"
                  exit 78
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
                  exit 0
                fi
                if [ "${1:-}" = "devices" ]; then
                  printf 'List of devices attached\n'
                  if [ "${FAKE_MULTIPLE_DEVICES:-0}" = "1" ]; then
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
                      echo "watch"
                      ;;
                    "shell pm list features")
                      echo "feature:android.hardware.type.watch"
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

    def run_launcher(self, extra_env=None):
        env = os.environ.copy()
        env["PATH"] = f"{self.bin}:{env['PATH']}"
        env["FAKE_HANDOFF_LOG"] = str(self.log)
        env["FAKE_FETCH_MARKER"] = str(self.fetch_marker)
        if extra_env:
            env.update(extra_env)
        return subprocess.run(
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

    def test_runs_verified_handoff_bound_to_single_galaxy_watch(self):
        result = self.run_launcher()

        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertTrue(self.fetch_marker.exists())
        lines = self.log.read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(lines), 2)
        self.assertTrue(lines[0].startswith("verify:"))
        self.assertTrue(lines[1].startswith("run:watch-1:"))
        self.assertTrue(lines[1].endswith(f":{self.profile.resolve()}"))

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
