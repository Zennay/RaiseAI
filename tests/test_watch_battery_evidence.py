import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "tools" / "compare-watch-battery-snapshots.py"


def load_tool():
    spec = importlib.util.spec_from_file_location("compare_watch_battery", TOOL)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


MODULE = load_tool()
REVISION = "8f719bb273f9b997848864f342598e7df5f090e5"


def snapshot(timestamp, percent, *, serial="watch-a", plugged=0, version="1.5.2", revision=REVISION):
    return {
        "schema_version": 1,
        "captured_at_utc": timestamp,
        "label": "test",
        "watch_serial": serial,
        "watch_model": "SM_L315F",
        "reported_watch_model": "SM_L315F",
        "app_version": version,
        "source_revision": revision,
        "battery_level": int(percent),
        "battery_scale": 100,
        "battery_percent": float(percent),
        "battery_status": 3,
        "plugged": plugged,
        "temperature_c": 31.2,
        "voltage_mv": 4100,
        "health": 2,
        "present": True,
        "technology": "Li-ion",
        "uptime_seconds": 12345.0,
        "wakefulness": "Awake",
        "read_only_capture": True,
    }


class BatterySnapshotComparisonTests(unittest.TestCase):
    def test_valid_unplugged_measurement(self):
        result = MODULE.compare(
            snapshot("2026-10-04T20:00:00Z", 90),
            snapshot("2026-10-04T22:00:00Z", 84),
            30,
        )
        self.assertTrue(result["measurement_valid"])
        self.assertEqual(result["battery_drop_percentage_points"], 6.0)
        self.assertEqual(result["battery_drop_pp_per_hour"], 3.0)
        self.assertEqual(result["duration_minutes"], 120.0)
        self.assertEqual(result["source_revision"], REVISION)

    def test_rejects_different_watch(self):
        with self.assertRaisesRegex(ValueError, "watch_serial"):
            MODULE.compare(
                snapshot("2026-10-04T20:00:00Z", 90, serial="watch-a"),
                snapshot("2026-10-04T22:00:00Z", 84, serial="watch-b"),
                30,
            )

    def test_rejects_plugged_measurement(self):
        with self.assertRaisesRegex(ValueError, "unplugged"):
            MODULE.compare(
                snapshot("2026-10-04T20:00:00Z", 90, plugged=1),
                snapshot("2026-10-04T22:00:00Z", 84),
                30,
            )

    def test_rejects_short_measurement(self):
        with self.assertRaisesRegex(ValueError, "too short"):
            MODULE.compare(
                snapshot("2026-10-04T20:00:00Z", 90),
                snapshot("2026-10-04T20:10:00Z", 89),
                30,
            )

    def test_rejects_battery_increase(self):
        with self.assertRaisesRegex(ValueError, "increased"):
            MODULE.compare(
                snapshot("2026-10-04T20:00:00Z", 80),
                snapshot("2026-10-04T22:00:00Z", 81),
                30,
            )

    def test_cli_writes_summary(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            start = tmp / "start.json"
            end = tmp / "end.json"
            output = tmp / "summary.json"
            start.write_text(json.dumps(snapshot("2026-10-04T20:00:00Z", 90)), encoding="utf-8")
            end.write_text(json.dumps(snapshot("2026-10-04T21:00:00Z", 87)), encoding="utf-8")

            completed = subprocess.run(
                [
                    sys.executable,
                    str(TOOL),
                    str(start),
                    str(end),
                    "--output",
                    str(output),
                ],
                check=False,
                text=True,
                capture_output=True,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            saved = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(saved["battery_drop_pp_per_hour"], 3.0)
            self.assertEqual(json.loads(completed.stdout), saved)


if __name__ == "__main__":
    unittest.main()
