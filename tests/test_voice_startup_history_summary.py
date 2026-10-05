import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools" / "summarize-voice-startup-history.py"
SOURCE = "a" * 40


def sample(latency: int, *, source: str = SOURCE, app: str = "1.5.2", attempt: int = 1, second: int = 0) -> dict:
    return {
        "schema_version": 1,
        "recorded_at_utc": f"2026-10-05T02:00:{second:02d}Z",
        "app_version": app,
        "source_revision": source,
        "attempt": attempt,
        "listen_request_to_ready_ms": latency,
    }


class VoiceStartupHistorySummaryTest(unittest.TestCase):
    def run_script(self, rows: list[dict], *args: str) -> subprocess.CompletedProcess[str]:
        with tempfile.TemporaryDirectory() as temp_dir:
            history = Path(temp_dir) / "voice-startup-evidence.jsonl"
            output = Path(temp_dir) / "summary.json"
            history.write_text(
                "".join(json.dumps(row) + "\n" for row in rows),
                encoding="utf-8",
            )
            completed = subprocess.run(
                [sys.executable, str(SCRIPT), str(history), "--output", str(output), *args],
                cwd=ROOT,
                capture_output=True,
                text=True,
                check=False,
            )
            if output.exists():
                completed.summary = json.loads(output.read_text(encoding="utf-8"))
            else:
                completed.summary = None
            return completed

    def test_summarizes_median_and_p95_without_threshold(self):
        result = self.run_script(
            [
                sample(100, attempt=1, second=1),
                sample(200, attempt=2, second=2),
                sample(500, attempt=3, second=3),
            ],
            "--min-samples",
            "3",
            "--expect-app-version",
            "1.5.2",
            "--expect-source-revision",
            SOURCE,
        )

        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual(3, result.summary["sample_count"])
        metrics = result.summary["listen_request_to_ready_ms"]
        self.assertEqual(100, metrics["min"])
        self.assertEqual(200, metrics["median"])
        self.assertEqual(500, metrics["p95_nearest_rank"])
        self.assertEqual(500, metrics["max"])

    def test_rejects_mixed_source_identity(self):
        result = self.run_script(
            [
                sample(100, source="a" * 40),
                sample(120, source="b" * 40, attempt=2, second=1),
            ]
        )

        self.assertEqual(2, result.returncode)
        self.assertIn("mixes source_revision", result.stderr)

    def test_rejects_too_few_samples(self):
        result = self.run_script([sample(100)], "--min-samples", "5")

        self.assertEqual(2, result.returncode)
        self.assertIn("need at least 5", result.stderr)

    def test_rejects_more_than_watch_history_bound(self):
        rows = [sample(100 + index, attempt=index + 1, second=index % 60) for index in range(51)]
        result = self.run_script(rows)

        self.assertEqual(2, result.returncode)
        self.assertIn("maximum is 50", result.stderr)


if __name__ == "__main__":
    unittest.main()
