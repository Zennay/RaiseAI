"""Metamorphic regression checks for the offline V1 Watch gesture acceptance gate.

These fixtures are synthetic, not evidence from a physical Galaxy Watch.
The frozen v1.5.2 artifact and physical acceptance issue #34 are unchanged.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest


MODULE = Path(__file__).resolve().parents[1] / "tools" / "analyze-watch-sensor-trials.py"
SPEC = importlib.util.spec_from_file_location("raise_v1_trial_metamorphic", MODULE)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("V1 trial analyzer module unavailable")
analyzer = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(analyzer)

REVISION = "8f719bb273f9b997848864f342598e7df5f090e5"
CONFIG = "calibration-v1;similarity=0.955"


def trial(session_id: int, label: str, triggered: bool, **overrides) -> dict:
    result = {
        "session_id": session_id,
        "label": label,
        "duration_ms": 3000,
        "sample_count": 20,
        "detector_triggered": triggered,
        "max_similarity": 0.98 if triggered else 0.7,
        "app_version": "1.5.2",
        "source_revision": REVISION,
        "detector_config": CONFIG,
    }
    result.update(overrides)
    return result


def boundary_dataset() -> list[dict]:
    """Exactly 27/30 detected raises and 5/100 unintended activations."""
    raises = [trial(i + 1, "mouth_raise", i < 27) for i in range(30)]
    negatives = [
        trial(i + 31, "view_time" if i % 2 else "normal_move", i < 5)
        for i in range(100)
    ]
    return raises + negatives


class WatchTrialMetamorphicQualityTests(unittest.TestCase):
    def test_exact_90_percent_and_5_percent_boundary_passes(self):
        report = analyzer.build_report(boundary_dataset())
        self.assertTrue(report["v1_gate_passed"])
        self.assertEqual(0.9, report["results"]["detection_rate"])
        self.assertEqual(0.05, report["results"]["false_trigger_rate"])
        self.assertEqual(0, report["rejected_trial_count"])

    def test_additional_missed_raise_flips_boundary_to_failure(self):
        items = boundary_dataset()
        items[0]["detector_triggered"] = False
        report = analyzer.build_report(items)
        self.assertFalse(report["v1_gate_passed"])
        self.assertEqual(26, report["results"]["mouth_raise_detected"])
        self.assertEqual(0.05, report["results"]["false_trigger_rate"])

    def test_additional_false_trigger_flips_boundary_to_failure(self):
        items = boundary_dataset()
        items[35]["detector_triggered"] = True
        report = analyzer.build_report(items)
        self.assertFalse(report["v1_gate_passed"])
        self.assertEqual(6, report["results"]["false_triggers"])
        self.assertEqual(0.9, report["results"]["detection_rate"])

    def test_extra_qualifying_missed_raise_cannot_improve_detection(self):
        items = boundary_dataset()
        items.append(trial(131, "mouth_raise", False))
        report = analyzer.build_report(items)
        self.assertFalse(report["v1_gate_passed"])
        self.assertEqual(31, report["results"]["mouth_raise_trials"])
        self.assertEqual(27, report["results"]["mouth_raise_detected"])
        self.assertLess(report["results"]["detection_rate"], 0.9)

    def test_extra_qualifying_false_trigger_cannot_dilute_failure(self):
        items = boundary_dataset()
        items.append(trial(131, "normal_move", True))
        report = analyzer.build_report(items)
        self.assertFalse(report["v1_gate_passed"])
        self.assertEqual(101, report["results"]["non_trigger_trials"])
        self.assertEqual(6, report["results"]["false_triggers"])
        self.assertGreater(report["results"]["false_trigger_rate"], 0.05)

    def test_rejected_noise_does_not_change_rates_or_counts(self):
        expected = analyzer.build_report(boundary_dataset())
        items = boundary_dataset()
        items.extend([
            trial(131, "mouth_raise", False, duration_ms=2999),
            trial(132, "normal_move", True, sample_count=19),
        ])
        result = analyzer.build_report(items)
        self.assertTrue(result["v1_gate_passed"])
        self.assertEqual(expected["results"], result["results"])
        self.assertEqual(2, result["rejected_trial_count"])

    def test_rejected_trial_with_other_calibration_still_fails_closed(self):
        items = boundary_dataset()
        items.append(
            trial(131, "normal_move", False, duration_ms=2999,
                  detector_config="other-calibration")
        )
        with self.assertRaisesRegex(analyzer.TrialError, "mix detector configurations"):
            analyzer.build_report(items)

    def test_trial_quality_cutoffs_are_inclusive_and_do_not_invent_trails(self):
        items = [
            trial(i + 1, "mouth_raise", True) for i in range(29)
        ] + [
            trial(i + 30, "normal_move", False) for i in range(99)
        ]
        items.extend([
            trial(129, "mouth_raise", True, duration_ms=2999),
            trial(130, "view_time", False, sample_count=19),
        ])
        before = analyzer.build_report(items)
        self.assertFalse(before["v1_gate_passed"])
        self.assertEqual(29, before["results"]["mouth_raise_trials"])
        self.assertEqual(99, before["results"]["non_trigger_trials"])
        self.assertEqual(2, before["rejected_trial_count"])

        items[-2]["duration_ms"] = 3000
        items[-1]["sample_count"] = 20
        after = analyzer.build_report(items)
        self.assertTrue(after["v1_gate_passed"])
        self.assertEqual(30, after["results"]["mouth_raise_trials"])
        self.assertEqual(100, after["results"]["non_trigger_trials"])
        self.assertEqual(0, after["rejected_trial_count"])


if __name__ == "__main__":
    unittest.main()
