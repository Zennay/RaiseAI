import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "tools" / "compare-watch-recovery-snapshots.py"
REVISION_A = "8f719bb273f9b997848864f342598e7df5f090e5"
REVISION_B = "1" * 40
APK_A = "a" * 64
APK_B = "b" * 64
BOOT_A = "11111111-1111-1111-1111-111111111111"
BOOT_B = "22222222-2222-2222-2222-222222222222"


def load_tool():
    spec = importlib.util.spec_from_file_location("compare_watch_recovery", TOOL)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


MODULE = load_tool()


def snapshot(
    timestamp,
    *,
    version="1.5.2",
    revision=REVISION_A,
    apk_sha=APK_A,
    boot_id=BOOT_A,
    uptime=3600.0,
    serial="watch-a",
    model="SM_L315F",
    monitoring=True,
    calibrated=True,
    service=True,
):
    return {
        "schema_version": 1,
        "captured_at_utc": timestamp,
        "label": "test",
        "watch_serial": serial,
        "watch_model": model,
        "app_version": version,
        "source_revision": revision,
        "installed_apk_sha256": apk_sha,
        "boot_id": boot_id,
        "uptime_seconds": uptime,
        "monitoring_enabled": monitoring,
        "calibrated": calibrated,
        "gesture_monitor_service_running": service,
        "read_only_capture": True,
    }


class RecoveryComparisonTests(unittest.TestCase):
    def test_valid_reboot_recovery(self):
        result = MODULE.compare(
            snapshot("2026-10-05T06:00:00Z", boot_id=BOOT_A, uptime=7200),
            snapshot("2026-10-05T06:05:00Z", boot_id=BOOT_B, uptime=120),
            mode="reboot",
        )
        self.assertTrue(result["recovery_valid"])
        self.assertEqual(result["mode"], "reboot")
        self.assertEqual(result["before"]["source_revision"], REVISION_A)
        self.assertEqual(result["after"]["installed_apk_sha256"], APK_A)
        self.assertTrue(result["gesture_monitor_service_running_after"])

    def test_reboot_rejects_same_boot_id(self):
        with self.assertRaisesRegex(ValueError, "different boot_id"):
            MODULE.compare(
                snapshot("2026-10-05T06:00:00Z", boot_id=BOOT_A),
                snapshot("2026-10-05T06:05:00Z", boot_id=BOOT_A),
                mode="reboot",
            )

    def test_reboot_rejects_app_identity_drift(self):
        with self.assertRaisesRegex(ValueError, "stable source_revision"):
            MODULE.compare(
                snapshot("2026-10-05T06:00:00Z", boot_id=BOOT_A),
                snapshot(
                    "2026-10-05T06:05:00Z",
                    boot_id=BOOT_B,
                    revision=REVISION_B,
                ),
                mode="reboot",
            )

    def test_rejects_recovery_when_monitoring_did_not_return(self):
        with self.assertRaisesRegex(ValueError, "GestureMonitorService running"):
            MODULE.compare(
                snapshot("2026-10-05T06:00:00Z", boot_id=BOOT_A),
                snapshot(
                    "2026-10-05T06:05:00Z",
                    boot_id=BOOT_B,
                    service=False,
                ),
                mode="reboot",
            )

    def test_rejects_recovery_when_monitoring_preference_disabled(self):
        with self.assertRaisesRegex(ValueError, "monitoring enabled"):
            MODULE.compare(
                snapshot("2026-10-05T06:00:00Z", boot_id=BOOT_A),
                snapshot(
                    "2026-10-05T06:05:00Z",
                    boot_id=BOOT_B,
                    monitoring=False,
                ),
                mode="reboot",
            )

    def test_valid_package_update_recovery(self):
        result = MODULE.compare(
            snapshot("2026-10-05T06:00:00Z", boot_id=BOOT_A),
            snapshot(
                "2026-10-05T06:03:00Z",
                boot_id=BOOT_A,
                version="1.6.0",
                revision=REVISION_B,
                apk_sha=APK_B,
                uptime=3780,
            ),
            mode="package-update",
        )
        self.assertTrue(result["recovery_valid"])
        self.assertEqual(result["mode"], "package-update")
        self.assertEqual(result["before"]["app_version"], "1.5.2")
        self.assertEqual(result["after"]["app_version"], "1.6.0")

    def test_package_update_requires_changed_source_revision(self):
        with self.assertRaisesRegex(ValueError, "changed source_revision"):
            MODULE.compare(
                snapshot("2026-10-05T06:00:00Z", boot_id=BOOT_A),
                snapshot(
                    "2026-10-05T06:03:00Z",
                    boot_id=BOOT_A,
                    version="1.6.0",
                    apk_sha=APK_B,
                ),
                mode="package-update",
            )

    def test_package_update_requires_changed_apk_digest(self):
        with self.assertRaisesRegex(ValueError, "changed installed_apk_sha256"):
            MODULE.compare(
                snapshot("2026-10-05T06:00:00Z", boot_id=BOOT_A),
                snapshot(
                    "2026-10-05T06:03:00Z",
                    boot_id=BOOT_A,
                    version="1.6.0",
                    revision=REVISION_B,
                ),
                mode="package-update",
            )

    def test_package_update_rejects_concurrent_reboot(self):
        with self.assertRaisesRegex(ValueError, "isolated from a Watch reboot"):
            MODULE.compare(
                snapshot("2026-10-05T06:00:00Z", boot_id=BOOT_A),
                snapshot(
                    "2026-10-05T06:03:00Z",
                    boot_id=BOOT_B,
                    version="1.6.0",
                    revision=REVISION_B,
                    apk_sha=APK_B,
                ),
                mode="package-update",
            )

    def test_rejects_different_watch(self):
        with self.assertRaisesRegex(ValueError, "watch_serial"):
            MODULE.compare(
                snapshot("2026-10-05T06:00:00Z", serial="watch-a"),
                snapshot(
                    "2026-10-05T06:05:00Z",
                    serial="watch-b",
                    boot_id=BOOT_B,
                ),
                mode="reboot",
            )

    def test_cli_writes_summary(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            before = root / "before.json"
            after = root / "after.json"
            output = root / "result.json"
            before.write_text(
                json.dumps(snapshot("2026-10-05T06:00:00Z", boot_id=BOOT_A)),
                encoding="utf-8",
            )
            after.write_text(
                json.dumps(
                    snapshot(
                        "2026-10-05T06:05:00Z",
                        boot_id=BOOT_B,
                        uptime=120,
                    )
                ),
                encoding="utf-8",
            )

            completed = subprocess.run(
                [
                    sys.executable,
                    str(TOOL),
                    str(before),
                    str(after),
                    "--mode",
                    "reboot",
                    "--output",
                    str(output),
                ],
                check=False,
                text=True,
                capture_output=True,
            )

            self.assertEqual(completed.returncode, 0, completed.stderr)
            saved = json.loads(output.read_text(encoding="utf-8"))
            self.assertTrue(saved["recovery_valid"])
            self.assertEqual(saved["mode"], "reboot")
            self.assertEqual(json.loads(completed.stdout), saved)


if __name__ == "__main__":
    unittest.main()
