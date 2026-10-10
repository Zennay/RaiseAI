"""End-to-end, no-network contracts for the macOS gesture Watch installer.

No Android SDK, physical watch, GitHub authentication or external network required:
fake tools exercise the exact branch/commit/CI-artifact and post-install gates.
"""

from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import textwrap
import unittest

ROOT = Path(__file__).resolve().parents[1]
INSTALLER = ROOT / "install-gesture-watch.command"
HEAD_SHA = "a" * 40
OTHER_SHA = "b" * 40


class MacGestureInstallerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="raise-gesture-test-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.bin = self.root / "bin"
        self.bin.mkdir()
        self.repo = self.root / "source"
        self.repo.mkdir()
        self.sdk = self.root / "sdk"
        (self.sdk / "platform-tools").mkdir(parents=True)
        shutil.copy2(INSTALLER, self.repo / INSTALLER.name)
        (self.repo / "VERSION.txt").write_text("1.5.4\n")
        self.install_log = self.root / "installed.txt"
        self.gh_log = self.root / "gh.txt"

        self.executable(
            self.bin / "uname",
            """#!/bin/bash
            echo Darwin
            """,
        )
        self.executable(
            self.bin / "git",
            """#!/bin/bash
            case "$1 $2" in
              "branch --show-current") printf '%s\\n' "${FAKE_BRANCH:-feature/gesture-permissions-setup-20261010}" ;;
              "status --porcelain") exit 0 ;;
              "rev-parse HEAD") printf '%s\\n' "$FAKE_HEAD_SHA" ;;
              "rev-parse FETCH_HEAD") printf '%s\\n' "${FAKE_REMOTE_SHA:-$FAKE_HEAD_SHA}" ;;
              "fetch --quiet") exit 0 ;;
              *) echo "unexpected git call: $*" >&2; exit 83 ;;
            esac
            """,
        )
        self.executable(
            self.bin / "gh",
            """#!/bin/bash
            printf '%s\\n' "$*" >> "$TEST_GH_LOG"
            case "$1 $2" in
              "auth status") exit 0 ;;
              "run list") printf '%s\\n' "${FAKE_RUN_ID-123}" ;;
              "run download")
                while [ "$#" -gt 0 ]; do
                  if [ "$1" = "--dir" ]; then
                    shift
                    mkdir -p "$1"
                    printf 'fake-apk' > "$1/app-debug.apk"
                    exit 0
                  fi
                  shift
                done
                exit 85
                ;;
              *) exit 86 ;;
            esac
            """,
        )
        self.executable(
            self.repo / "install-watch-apk.command",
            """#!/bin/bash
            printf 'ci:%s\\n' "$1" >> "$TEST_INSTALL_LOG"
            echo watch-serial > "$RAISE_INSTALLED_WATCH_SERIAL_FILE"
            printf 'fake-digest\\n' > "$RAISE_INSTALLED_APK_SHA256_FILE"
            """,
        )
        self.executable(
            self.repo / "upgrade-watch.command",
            """#!/bin/bash
            echo local >> "$TEST_INSTALL_LOG"
            echo watch-serial > "$RAISE_INSTALLED_WATCH_SERIAL_FILE"
            printf 'fake-digest\\n' > "$RAISE_INSTALLED_APK_SHA256_FILE"
            """,
        )
        self.executable(
            self.sdk / "platform-tools" / "adb",
            """#!/bin/bash
            if [[ "$*" == *"shell dumpsys package nl.zennay.raiseai"* ]]; then
              printf '  versionCode=%s minSdk=30\\n' "${FAKE_VERSION_CODE:-21}"
              printf '  versionName=%s\\n' "${FAKE_VERSION_NAME:-1.5.4}"
              exit 0
            fi
            echo "unexpected adb call" >&2
            exit 91
            """,
        )
        self.env = dict(
            os.environ,
            PATH=str(self.bin) + os.pathsep + os.environ["PATH"],
            ANDROID_SDK_ROOT=str(self.sdk),
            TEST_INSTALL_LOG=str(self.install_log),
            TEST_GH_LOG=str(self.gh_log),
            FAKE_HEAD_SHA=HEAD_SHA,
            RAISE_INSTALL_FROM="ci",
        )

    @staticmethod
    def executable(path: Path, contents: str) -> None:
        path.write_text(textwrap.dedent(contents).lstrip())
        path.chmod(0o755)

    def run_installer(self, **overrides: str) -> subprocess.CompletedProcess[str]:
        env = dict(self.env, **overrides)
        return subprocess.run(
            ["bash", str(self.repo / INSTALLER.name)],
            cwd=self.repo,
            env=env,
            text=True,
            capture_output=True,
            timeout=15,
            check=False,
        )

    def test_script_parses_in_bash(self) -> None:
        completed = subprocess.run(
            ["bash", "-n", str(INSTALLER)], text=True, capture_output=True, check=False
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)

    def test_exact_ci_artifact_installs_and_checks_version(self) -> None:
        completed = self.run_installer()
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        self.assertIn("SUCCESS: Raise AI gesture v1.5.4", completed.stdout)
        self.assertIn("ci:", self.install_log.read_text())
        self.assertIn("--name RaiseAI-Watch7-v1.5.4-123", self.gh_log.read_text())

    def test_missing_ci_artifact_falls_back_only_to_local_build(self) -> None:
        completed = self.run_installer(RAISE_INSTALL_FROM="auto", FAKE_RUN_ID="")
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        self.assertEqual(self.install_log.read_text(), "local\n")

    def test_ci_only_mode_never_installs_an_untested_build(self) -> None:
        completed = self.run_installer(FAKE_RUN_ID="")
        self.assertNotEqual(completed.returncode, 0)
        self.assertIn("No successful CI artifact", completed.stderr)
        self.assertFalse(self.install_log.exists())

    def test_rejects_main_branch_without_installing(self) -> None:
        completed = self.run_installer(FAKE_BRANCH="main")
        self.assertNotEqual(completed.returncode, 0)
        self.assertIn("Wrong branch", completed.stderr)
        self.assertFalse(self.install_log.exists())

    def test_rejects_stale_feature_checkout(self) -> None:
        completed = self.run_installer(FAKE_REMOTE_SHA=OTHER_SHA)
        self.assertNotEqual(completed.returncode, 0)
        self.assertIn("Feature branch was updated", completed.stderr)
        self.assertFalse(self.install_log.exists())

    def test_rejects_incorrect_installed_watch_version(self) -> None:
        completed = self.run_installer(FAKE_VERSION_NAME="1.5.3")
        self.assertNotEqual(completed.returncode, 0)
        self.assertIn("does not report installed version 1.5.4", completed.stderr)

    def test_rejects_incorrect_installed_version_code(self) -> None:
        completed = self.run_installer(FAKE_VERSION_CODE="20")
        self.assertNotEqual(completed.returncode, 0)
        self.assertIn("versionCode=21", completed.stderr)


if __name__ == "__main__":
    unittest.main()
