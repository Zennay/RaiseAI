"""Exercise the V1 trial analyzer's machine-readable command-line exit contract.

All CSV data here is synthetic; a green test is not Watch hardware acceptance.
"""

from contextlib import redirect_stdout
import csv
import importlib.util
from io import StringIO
import json
from pathlib import Path
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "raise_trial_cli_status_analyzer", ROOT / "tools" / "analyze-watch-sensor-trials.py"
)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("V1 trial analyzer is missing")
analyzer = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(analyzer)

COLUMNS = [
    "label", "session_id", "duration_ms", "sample_count",
    "detector_triggered", "max_similarity", "app_version",
    "source_revision", "detector_config",
]
FROZEN_SHA = "8f719bb273f9b997848864f342598e7df5f090e5"


def example_rows(raises: int, movements: int) -> list[dict[str, str]]:
    rows = []
    for index in range(raises + movements):
        is_raise = index < raises
        rows.append({
            "label": "mouth_raise" if is_raise else (
                "view_time" if index % 2 else "normal_move"
            ),
            "session_id": str(index + 1),
            "duration_ms": "4000",
            "sample_count": "40",
            "detector_triggered": "true" if is_raise else "false",
            "max_similarity": "0.98" if is_raise else "0.60",
            "app_version": "1.5.2",
            "source_revision": FROZEN_SHA,
            "detector_config": "watch-v1;similarity=0.955",
        })
    return rows


class WatchTrialCliExitCodeContract(unittest.TestCase):
    def run_cli(
        self,
        rows: list[dict[str, str]],
        *args: str,
        columns: list[str] | None = None,
    ) -> tuple[int, dict]:
        with tempfile.TemporaryDirectory(prefix="raise-trial-cli-") as tmp:
            csv_path = Path(tmp) / "trials.csv"
            with csv_path.open("w", encoding="utf-8", newline="") as stream:
                writer = csv.DictWriter(stream, fieldnames=columns or COLUMNS)
                writer.writeheader()
                writer.writerows(rows)
            output = StringIO()
            with redirect_stdout(output):
                exit_code = analyzer.main([str(csv_path), *args])
        return exit_code, json.loads(output.getvalue())

    def test_exact_30_100_v1_gate_returns_zero_and_evidence_counts(self):
        code, result = self.run_cli(example_rows(30, 100), "--require-v1-gate")
        self.assertEqual(0, code)
        self.assertTrue(result["v1_gate_passed"])
        self.assertEqual(30, result["results"]["mouth_raise_trials"])
        self.assertEqual(100, result["results"]["non_trigger_trials"])

    def test_insufficient_raise_count_requires_nonzero_with_truthful_report(self):
        rows = example_rows(29, 100)
        code, payload = self.run_cli(rows, "--require-v1-gate")
        self.assertEqual(1, code)
        self.assertFalse(payload["v1_gate_passed"])
        self.assertEqual(1, payload["remaining"]["mouth_raise_trials"])
        informational_code, informational = self.run_cli(rows)
        self.assertEqual(0, informational_code)
        self.assertFalse(informational["v1_gate_passed"])

    def test_insufficient_nontrigger_count_requires_nonzero(self):
        code, result = self.run_cli(example_rows(30, 99), "--require-v1-gate")
        self.assertEqual(1, code)
        self.assertFalse(result["v1_gate_passed"])
        self.assertEqual(1, result["remaining"]["non_trigger_trials"])

    def test_bad_trigger_value_is_a_machine_readable_invalid_input(self):
        rows = example_rows(1, 1)
        rows[0]["detector_triggered"] = "maybe"
        code, result = self.run_cli(rows, "--require-v1-gate")
        self.assertEqual(2, code)
        self.assertIs(result["valid"], False)
        self.assertIn("detector_triggered", result["reason"])

    def test_unexpected_csv_column_is_not_silently_ignored(self):
        rows = example_rows(1, 1)
        for row in rows:
            row["raw_transcript"] = "must-not-be-present"
        code, result = self.run_cli(rows, columns=COLUMNS + ["raw_transcript"])
        self.assertEqual(2, code)
        self.assertIs(result["valid"], False)
        self.assertIn("unexpected columns", result["reason"])
        self.assertNotIn("must-not-be-present", json.dumps(result))

    def test_expected_frozen_source_mismatch_is_invalid_not_low_scoring(self):
        code, result = self.run_cli(
            example_rows(30, 100),
            "--expect-source-revision", "0" * 40,
            "--require-v1-gate",
        )
        self.assertEqual(2, code)
        self.assertIs(result["valid"], False)
        self.assertIn("does not match expected", result["reason"])

    def test_invalid_minimum_rate_is_rejected_before_scoring(self):
        code, result = self.run_cli(
            example_rows(30, 100),
            "--min-detection-rate", "1.01",
            "--require-v1-gate",
        )
        self.assertEqual(2, code)
        self.assertIs(result["valid"], False)
        self.assertIn("thresholds", result["reason"])
