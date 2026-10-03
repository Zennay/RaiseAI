import importlib.util
import pathlib
import tempfile
import unittest

MODULE_PATH = pathlib.Path(__file__).resolve().parents[1] / "tools" / "analyze-watch-sensor-trials.py"
SPEC = importlib.util.spec_from_file_location("watch_trial_analyzer", MODULE_PATH)
analyzer = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(analyzer)


def trial(label, session_id, triggered, *, duration_ms=4000, sample_count=40):
    return {
        "label": label,
        "session_id": session_id,
        "duration_ms": duration_ms,
        "sample_count": sample_count,
        "detector_triggered": triggered,
        "max_similarity": 0.98 if triggered else 0.88,
    }


class WatchTrialAnalyzerTests(unittest.TestCase):
    def test_passes_roadmap_gate_at_90_percent_detection_and_5_percent_false_triggers(self):
        trials = []
        sid = 1
        for index in range(30):
            trials.append(trial("mouth_raise", sid, index < 27))
            sid += 1
        for index in range(50):
            trials.append(trial("view_time", sid, index < 2))
            sid += 1
        for index in range(50):
            trials.append(trial("normal_move", sid, index < 3))
            sid += 1

        report = analyzer.build_report(trials)
        self.assertTrue(report["v1_gate_passed"])
        self.assertEqual(report["results"]["detection_rate"], 0.9)
        self.assertEqual(report["results"]["false_trigger_rate"], 0.05)

    def test_fails_when_detection_rate_is_below_target(self):
        trials = [trial("mouth_raise", sid, sid <= 26) for sid in range(1, 31)]
        trials += [trial("normal_move", sid, False) for sid in range(31, 131)]
        report = analyzer.build_report(trials)
        self.assertFalse(report["v1_gate_passed"])
        self.assertLess(report["results"]["detection_rate"], 0.9)

    def test_fails_when_false_trigger_rate_is_above_target(self):
        trials = [trial("mouth_raise", sid, True) for sid in range(1, 31)]
        trials += [trial("normal_move", sid, sid < 37) for sid in range(31, 131)]
        report = analyzer.build_report(trials)
        self.assertFalse(report["v1_gate_passed"])
        self.assertGreater(report["results"]["false_trigger_rate"], 0.05)

    def test_short_trials_are_rejected_from_denominator(self):
        trials = [trial("mouth_raise", 1, True, duration_ms=1000, sample_count=10)]
        report = analyzer.build_report(
            trials,
            required_raises=1,
            required_non_triggers=0,
        )
        self.assertFalse(report["v1_gate_passed"])
        self.assertEqual(report["results"]["mouth_raise_trials"], 0)
        self.assertEqual(report["rejected_trial_count"], 1)

    def test_read_trials_rejects_duplicate_session(self):
        content = (
            "label,session_id,duration_ms,sample_count,detector_triggered,max_similarity\n"
            "mouth_raise,1,4000,40,true,0.98\n"
            "view_time,1,4000,40,false,0.80\n"
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / "sensor-trials.csv"
            path.write_text(content, encoding="utf-8")
            with self.assertRaisesRegex(analyzer.TrialError, "duplicate session_id"):
                analyzer.read_trials(path)


if __name__ == "__main__":
    unittest.main()
