"""Regression tests for V1 trace reporting (no physical PASS implied)."""

import importlib.util
from pathlib import Path
import unittest

MODULE_PATH = Path(__file__).resolve().parents[1] / "tools" / "analyze-watch-sensor-traces.py"
spec = importlib.util.spec_from_file_location("raise_trace_report_under_test", MODULE_PATH)
module = importlib.util.module_from_spec(spec)
import sys
sys.modules[spec.name] = module
spec.loader.exec_module(module)


def session(identifier, label, qualifying=True):
    return module.SessionSummary(
        session_id=identifier,
        label=label,
        sample_count=20 if qualifying else 1,
        duration_ms=3000 if qualifying else 0,
        monotonic=True,
        qualifying=qualifying,
    )


class TraceReportContractTests(unittest.TestCase):
    def test_empty_input_never_ready(self):
        report = module.build_report([])
        self.assertFalse(report["ready_for_v1_reliability_test"])
        self.assertEqual(report["remaining"], {"mouth_raise": 30, "non_trigger_total": 100})

    def test_both_independent_thresholds_required(self):
        raises = [session(i, "mouth_raise") for i in range(1, 31)]
        negatives = [session(i, "normal_move") for i in range(31, 131)]
        self.assertFalse(module.build_report(raises)["ready_for_v1_reliability_test"])
        self.assertFalse(module.build_report(negatives)["ready_for_v1_reliability_test"])
        self.assertTrue(module.build_report(raises + negatives)["ready_for_v1_reliability_test"])

    def test_non_trigger_categories_combine_without_counting_raises(self):
        data = [session(i, "mouth_raise") for i in range(1, 31)]
        data += [session(i, "view_time") for i in range(31, 81)]
        data += [session(i, "normal_move") for i in range(81, 131)]
        report = module.build_report(data)
        self.assertEqual(report["qualified"]["non_trigger_total"], 100)
        self.assertEqual(report["qualified"]["view_time"], 50)
        self.assertEqual(report["qualified"]["normal_move"], 50)
        self.assertEqual(report["qualified"]["total"], 130)

    def test_rejected_sessions_never_satisfy_gate(self):
        data = [session(i, "mouth_raise") for i in range(1, 30)]
        data += [session(30, "mouth_raise", qualifying=False)]
        data += [session(i, "normal_move") for i in range(31, 131)]
        report = module.build_report(data)
        self.assertFalse(report["ready_for_v1_reliability_test"])
        self.assertEqual(report["captured"]["mouth_raise"], 30)
        self.assertEqual(report["qualified"]["mouth_raise"], 29)
        self.assertEqual(report["remaining"]["mouth_raise"], 1)
        self.assertEqual([item["session_id"] for item in report["rejected_sessions"]], [30])

    def test_exact_boundary_and_overage_are_ready(self):
        data = [session(i, "mouth_raise") for i in range(1, 32)]
        data += [session(i, "view_time") for i in range(32, 133)]
        report = module.build_report(data)
        self.assertTrue(report["ready_for_v1_reliability_test"])
        self.assertEqual(report["remaining"], {"mouth_raise": 0, "non_trigger_total": 0})

    def test_negative_required_counts_fail_closed(self):
        for raise_requirement, negative_requirement in [(-1, 100), (30, -1)]:
            with self.subTest(raise_requirement=raise_requirement, negative_requirement=negative_requirement):
                with self.assertRaises(module.TraceError):
                    module.build_report([], required_raises=raise_requirement,
                                        required_non_triggers=negative_requirement)


if __name__ == "__main__":
    unittest.main()
