"""V1 Watch reliability gates must use exact rates, not rounded report fields.

Standalone synthetic regression tests. These are NOT physical Watch acceptance
records and do not modify the frozen v1.5.2 handoff or issue #34.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest


SOURCE = Path(__file__).resolve().parents[1] / "tools" / "analyze-watch-sensor-trials.py"
SPEC = importlib.util.spec_from_file_location("raise_watch_trial_rate_precision", SOURCE)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("Watch V1 trial analyzer unavailable")
analyzer = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(analyzer)

FROZEN_REVISION = "8f719bb273f9b997848864f342598e7df5f090e5"


def trial(session_id: int, label: str, triggered: bool) -> dict:
    return {
        "session_id": session_id,
        "label": label,
        "duration_ms": 3000,
        "sample_count": 20,
        "detector_triggered": triggered,
        "max_similarity": 0.97 if triggered else 0.70,
        "app_version": "1.5.2",
        "source_revision": FROZEN_REVISION,
        "detector_config": "calibration-v1;similarity=0.955",
    }


def report(detected_raises: int, false_triggers: int, **thresholds) -> dict:
    items = [
        trial(i + 1, "mouth_raise", i < detected_raises)
        for i in range(3)
    ]
    items.extend(
        trial(i + 4, "view_time" if i % 2 else "normal_move", i < false_triggers)
        for i in range(3)
    )
    return analyzer.build_report(
        items,
        required_raises=3,
        required_non_triggers=3,
        **thresholds,
    )


class V1WatchTrialRatePrecisionContract(unittest.TestCase):
    def test_detection_fraction_one_third_above_threshold_despite_round_down(self):
        result = report(
            1, 0,
            min_detection_rate=0.3333331,
            max_false_trigger_rate=0.0,
        )
        self.assertEqual(0.333333, result["results"]["detection_rate"])
        self.assertTrue(result["v1_gate_passed"])

    def test_detection_fraction_two_thirds_below_threshold_despite_round_up(self):
        result = report(
            2, 0,
            min_detection_rate=0.6666669,
            max_false_trigger_rate=0.0,
        )
        self.assertEqual(0.666667, result["results"]["detection_rate"])
        self.assertFalse(result["v1_gate_passed"])

    def test_false_trigger_fraction_one_third_exceeds_limit_despite_round_down(self):
        result = report(
            3, 1,
            min_detection_rate=1.0,
            max_false_trigger_rate=0.3333331,
        )
        self.assertEqual(0.333333, result["results"]["false_trigger_rate"])
        self.assertFalse(result["v1_gate_passed"])

    def test_false_trigger_fraction_two_thirds_within_limit_despite_round_up(self):
        result = report(
            3, 2,
            min_detection_rate=1.0,
            max_false_trigger_rate=0.6666669,
        )
        self.assertEqual(0.666667, result["results"]["false_trigger_rate"])
        self.assertTrue(result["v1_gate_passed"])

    def test_exact_rational_boundaries_are_inclusive_for_both_rates(self):
        result = report(
            1, 1,
            min_detection_rate=1 / 3,
            max_false_trigger_rate=1 / 3,
        )
        self.assertTrue(result["v1_gate_passed"])
        self.assertEqual(0, result["remaining"]["mouth_raise_trials"])
        self.assertEqual(0, result["remaining"]["non_trigger_trials"])


if __name__ == "__main__":
    unittest.main()
