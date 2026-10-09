"""Independent V1 trial gate matrix for physical Watch acceptance reporting.

These are synthetic, offline tests. They do not provide device evidence and
must never be presented as a pass for the physical Watch gate.
"""

import importlib.util
from pathlib import Path
import unittest


ANALYZER_FILE = Path(__file__).resolve().parents[1] / "tools" / "analyze-watch-sensor-trials.py"
SPEC = importlib.util.spec_from_file_location("raise_v1_trial_matrix_analyzer", ANALYZER_FILE)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("Watch trial analyzer module unavailable")
analyzer = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(analyzer)

SOURCE = "8f719bb273f9b997848864f342598e7df5f090e5"


def observation(
    session_id: int,
    label: str,
    triggered: bool = False,
    *,
    duration_ms: int = 3_000,
    sample_count: int = 20,
) -> dict:
    return {
        "label": label,
        "session_id": session_id,
        "duration_ms": duration_ms,
        "sample_count": sample_count,
        "detector_triggered": triggered,
        "max_similarity": 0.98 if triggered else 0.70,
        "app_version": "1.5.2",
        "source_revision": SOURCE,
        "detector_config": "calibration-v1;similarity=0.955",
    }


def dataset(raises: int, non_triggers: int) -> list[dict]:
    return [
        observation(i + 1, "mouth_raise", True)
        for i in range(raises)
    ] + [
        observation(i + 1 + raises, "view_time" if i % 2 else "normal_move")
        for i in range(non_triggers)
    ]


class WatchV1TrialGateMatrix(unittest.TestCase):
    def test_exact_30_100_counts_and_minimum_per_trial_samples_pass(self):
        report = analyzer.build_report(dataset(30, 100))
        self.assertTrue(report["v1_gate_passed"])
        self.assertEqual(30, report["results"]["mouth_raise_trials"])
        self.assertEqual(100, report["results"]["non_trigger_trials"])
        self.assertEqual(0, report["rejected_trial_count"])

    def test_29_intentional_trials_fail_even_with_perfect_detection(self):
        report = analyzer.build_report(dataset(29, 100))
        self.assertFalse(report["v1_gate_passed"])
        self.assertEqual(1, report["remaining"]["mouth_raise_trials"])

    def test_99_nontrigger_trials_fail_even_with_zero_false_triggers(self):
        report = analyzer.build_report(dataset(30, 99))
        self.assertFalse(report["v1_gate_passed"])
        self.assertEqual(1, report["remaining"]["non_trigger_trials"])

    def test_both_nontrigger_categories_contribute_to_one_denominator(self):
        trials = [observation(i + 1, "mouth_raise", True) for i in range(30)]
        trials += [
            observation(31 + i, "view_time" if i < 40 else "normal_move", i < 5)
            for i in range(100)
        ]
        report = analyzer.build_report(trials)
        self.assertTrue(report["v1_gate_passed"])
        self.assertEqual(100, report["results"]["non_trigger_trials"])
        self.assertEqual(5, report["results"]["false_triggers"])
        self.assertEqual(0.05, report["results"]["false_trigger_rate"])

    def test_noise_below_either_quality_boundary_never_fills_count_gate(self):
        trials = dataset(29, 99)
        trials += [
            observation(129, "mouth_raise", True, duration_ms=2_999),
            observation(130, "normal_move", False, sample_count=19),
        ]
        report = analyzer.build_report(trials)
        self.assertFalse(report["v1_gate_passed"])
        self.assertEqual(2, report["rejected_trial_count"])
        self.assertEqual(1, report["remaining"]["mouth_raise_trials"])
        self.assertEqual(1, report["remaining"]["non_trigger_trials"])

    def test_out_of_order_trials_have_identical_counts_rates_and_gate(self):
        trials = dataset(30, 100)
        trials[2]["detector_triggered"] = False
        trials[34]["detector_triggered"] = True
        a = analyzer.build_report(trials)
        b = analyzer.build_report(list(reversed(trials)))
        self.assertEqual(a, b)

    def test_extraneous_low_quality_miss_cannot_dilute_detection_rate(self):
        trials = dataset(30, 100)
        trials += [observation(131, "mouth_raise", False, sample_count=19)]
        report = analyzer.build_report(trials)
        self.assertEqual(1.0, report["results"]["detection_rate"])
        self.assertEqual(30, report["results"]["mouth_raise_trials"])
        self.assertEqual(1, report["rejected_trial_count"])

    def test_invalid_rate_and_count_thresholds_are_rejected(self):
        trials = dataset(1, 1)
        for option in (
            {"required_raises": -1},
            {"required_non_triggers": -1},
            {"min_detection_rate": -0.01},
            {"min_detection_rate": 1.01},
            {"max_false_trigger_rate": -0.01},
            {"max_false_trigger_rate": 1.01},
            {"min_samples": 0},
            {"min_duration_ms": -1},
        ):
            with self.subTest(option=option):
                with self.assertRaises(analyzer.TrialError):
                    analyzer.build_report(trials, **option)

    def test_frozen_source_identity_is_preserved_in_report(self):
        report = analyzer.build_report(dataset(30, 100), expect_source_revision=SOURCE)
        self.assertEqual(SOURCE, report["evidence_identity"]["source_revision"])
        with self.assertRaisesRegex(analyzer.TrialError, "does not match expected"):
            analyzer.build_report(
                dataset(30, 100),
                expect_source_revision="0" * 40,
            )
