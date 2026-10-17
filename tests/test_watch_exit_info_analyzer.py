import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "tools" / "analyze-watch-exit-info.py"
REVISION = "8f719bb273f9b997848864f342598e7df5f090e5"
APK_SHA = "a" * 64


def load_tool():
    spec = importlib.util.spec_from_file_location("watch_exit_info", TOOL)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


MODULE = load_tool()


def dump(*entries: str) -> str:
    body = "\n".join(entries)
    return (
        "ACTIVITY MANAGER PROCESS EXIT INFO (dumpsys activity exit-info)\n"
        "Last Timestamp of Persistence Into Persistent Storage: 2026-10-05 06:00:00.000\n"
        "  package: nl.zennay.raiseai\n"
        "    Historical Process Exit for uid=10123\n"
        f"{body}\n"
    )


def entry(index: int, timestamp: str, reason: int, label: str, status: int = 0, process: str = "nl.zennay.raiseai") -> str:
    return (
        f"        ApplicationExitInfo #{index}:\n"
        f"          timestamp={timestamp}\n"
        "          pid=1234\n"
        "          realUid=10123\n"
        "          packageUid=10123\n"
        "          definingUid=10123\n"
        "          user=0\n"
        f"          process={process}\n"
        f"          reason={reason} ({label})\n"
        f"          status={status}\n"
        "          importance=100\n"
        "          pss=0.00\n"
        "          rss=0.00\n"
        "          description=null\n"
        "          state=empty\n"
        "          trace=null"
    )


def analyze(text: str, *, service_running: bool = True):
    return MODULE.analyze(
        text,
        session_start="2026-10-05T05:00:00Z",
        device_utc_offset="+0100",
        package="nl.zennay.raiseai",
        watch_serial="watch-a",
        watch_model="SM_L315F",
        app_version="1.5.2",
        source_revision=REVISION,
        installed_apk_sha256=APK_SHA,
        service_running=service_running,
    )


class WatchExitInfoAnalyzerTests(unittest.TestCase):
    def test_clean_session_accepts_noncritical_exit(self):
        result = analyze(
            dump(entry(0, "2026-10-05 06:15:00.000", 10, "USER REQUESTED"))
        )
        self.assertTrue(result["stability_valid"])
        self.assertEqual(result["critical_exit_count"], 0)
        self.assertEqual(result["scoped_exit_count"], 1)

    def test_java_crash_fails_gate(self):
        result = analyze(
            dump(entry(0, "2026-10-05 06:15:00.000", 4, "APP CRASH(EXCEPTION)", 1))
        )
        self.assertFalse(result["stability_valid"])
        self.assertEqual(result["critical_exit_count"], 1)
        self.assertEqual(result["critical_reasons"], ["REASON_CRASH"])

    def test_native_crash_and_anr_fail_gate(self):
        result = analyze(
            dump(
                entry(0, "2026-10-05 06:16:00.000", 5, "APP CRASH(NATIVE)", 11),
                entry(1, "2026-10-05 06:17:00.000", 6, "ANR", 0),
            )
        )
        self.assertFalse(result["stability_valid"])
        self.assertEqual(result["critical_exit_count"], 2)
        self.assertEqual(
            result["critical_reasons"],
            ["REASON_ANR", "REASON_CRASH_NATIVE"],
        )

    def test_pre_session_crash_is_not_counted(self):
        result = analyze(
            dump(entry(0, "2026-10-05 05:59:59.000", 4, "APP CRASH(EXCEPTION)", 1))
        )
        self.assertTrue(result["stability_valid"])
        self.assertEqual(result["scoped_exit_count"], 0)

    def test_child_process_is_scoped_to_package(self):
        result = analyze(
            dump(
                entry(
                    0,
                    "2026-10-05 06:20:00.000",
                    4,
                    "APP CRASH(EXCEPTION)",
                    1,
                    process="nl.zennay.raiseai:worker",
                )
            )
        )
        self.assertFalse(result["stability_valid"])

    def test_other_package_is_ignored(self):
        result = analyze(
            dump(
                entry(
                    0,
                    "2026-10-05 06:20:00.000",
                    4,
                    "APP CRASH(EXCEPTION)",
                    1,
                    process="com.example.other",
                )
            )
        )
        self.assertTrue(result["stability_valid"])
        self.assertEqual(result["scoped_exit_count"], 0)

    def test_inactive_gesture_service_fails_gate_without_crash(self):
        result = analyze(dump(), service_running=False)
        self.assertFalse(result["stability_valid"])
        self.assertEqual(result["critical_exit_count"], 0)

    def test_rejects_malformed_dump(self):
        with self.assertRaisesRegex(ValueError, "not an Android activity exit-info dump"):
            analyze("not a dumpsys result")

    def test_cli_writes_machine_readable_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            raw = root / "exit-info.txt"
            output = root / "stability.json"
            raw.write_text(
                dump(entry(0, "2026-10-05 06:15:00.000", 6, "ANR", 0)),
                encoding="utf-8",
            )

            completed = subprocess.run(
                [
                    sys.executable,
                    str(TOOL),
                    str(raw),
                    "--session-start",
                    "2026-10-05T05:00:00Z",
                    "--device-utc-offset",
                    "+0100",
                    "--watch-serial",
                    "watch-a",
                    "--watch-model",
                    "SM_L315F",
                    "--app-version",
                    "1.5.2",
                    "--source-revision",
                    REVISION,
                    "--installed-apk-sha256",
                    APK_SHA,
                    "--service-running",
                    "true",
                    "--output",
                    str(output),
                ],
                check=False,
                text=True,
                capture_output=True,
            )

            self.assertEqual(completed.returncode, 1, completed.stderr)
            saved = json.loads(output.read_text(encoding="utf-8"))
            self.assertFalse(saved["stability_valid"])
            self.assertEqual(saved["critical_reasons"], ["REASON_ANR"])


if __name__ == "__main__":
    unittest.main()
