import importlib.util
import pathlib
import sys
import tempfile
import unittest

MODULE_PATH = pathlib.Path(__file__).resolve().parents[1] / "tools" / "analyze-watch-sensor-traces.py"
SPEC = importlib.util.spec_from_file_location("watch_trace_analyzer", MODULE_PATH)
analyzer = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = analyzer
SPEC.loader.exec_module(analyzer)


def make_session(session_id, label, *, samples=25, step_ms=150):
    return [
        analyzer.Sample(
            label=label,
            session_id=session_id,
            elapsed_ms=index * step_ms,
            x=0.1,
            y=0.2,
            z=9.7,
        )
        for index in range(samples)
    ]


class WatchTraceAnalyzerTests(unittest.TestCase):
    def test_reports_v1_gate_ready_at_30_raises_and_100_non_triggers(self):
        samples = []
        session_id = 1
        for _ in range(30):
            samples.extend(make_session(session_id, "mouth_raise"))
            session_id += 1
        for _ in range(50):
            samples.extend(make_session(session_id, "view_time"))
            session_id += 1
        for _ in range(50):
            samples.extend(make_session(session_id, "normal_move"))
            session_id += 1

        sessions = analyzer.summarize_sessions(samples)
        report = analyzer.build_report(sessions)

        self.assertTrue(report["ready_for_v1_reliability_test"])
        self.assertEqual(report["qualified"]["mouth_raise"], 30)
        self.assertEqual(report["qualified"]["non_trigger_total"], 100)
        self.assertEqual(report["rejected_sessions"], [])

    def test_short_capture_does_not_count(self):
        samples = make_session(1, "mouth_raise", samples=10, step_ms=100)
        sessions = analyzer.summarize_sessions(samples)
        report = analyzer.build_report(sessions, required_raises=1, required_non_triggers=0)

        self.assertFalse(report["ready_for_v1_reliability_test"])
        self.assertEqual(report["qualified"]["mouth_raise"], 0)
        self.assertEqual(report["captured"]["mouth_raise"], 1)
        self.assertEqual(len(report["rejected_sessions"]), 1)

    def test_non_monotonic_elapsed_time_is_rejected(self):
        samples = make_session(1, "normal_move")
        samples[8] = analyzer.Sample("normal_move", 1, 50, 0.1, 0.2, 9.7)
        sessions = analyzer.summarize_sessions(samples)
        self.assertFalse(sessions[0].monotonic)
        self.assertFalse(sessions[0].qualifying)

    def test_read_samples_rejects_mixed_labels_for_same_session(self):
        content = (
            "label,session_id,elapsed_ms,x,y,z\n"
            "mouth_raise,123,0,0.1,0.2,9.7\n"
            "view_time,123,100,0.1,0.2,9.7\n"
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / "traces.csv"
            path.write_text(content, encoding="utf-8")
            with self.assertRaisesRegex(analyzer.TraceError, "mixes labels"):
                analyzer.read_samples(path)

    def test_read_samples_rejects_unknown_columns(self):
        content = "label,session_id,elapsed_ms,x,y,z,secret\nmouth_raise,1,0,0,0,9.8,nope\n"
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / "traces.csv"
            path.write_text(content, encoding="utf-8")
            with self.assertRaisesRegex(analyzer.TraceError, "unexpected columns"):
                analyzer.read_samples(path)

    def test_read_samples_rejects_nan_sensor_value(self):
        content = "label,session_id,elapsed_ms,x,y,z\nmouth_raise,1,0,nan,0.2,9.7\n"
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / "traces.csv"
            path.write_text(content, encoding="utf-8")
            with self.assertRaisesRegex(analyzer.TraceError, "x must be a finite number"):
                analyzer.read_samples(path)

    def test_read_samples_rejects_infinite_sensor_value(self):
        content = "label,session_id,elapsed_ms,x,y,z\nmouth_raise,1,0,0.1,inf,9.7\n"
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / "traces.csv"
            path.write_text(content, encoding="utf-8")
            with self.assertRaisesRegex(analyzer.TraceError, "y must be a finite number"):
                analyzer.read_samples(path)


if __name__ == "__main__":
    unittest.main()
