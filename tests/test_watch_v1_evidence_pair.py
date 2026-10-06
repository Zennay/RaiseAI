import importlib.util
import pathlib
import tempfile
import unittest


MODULE_PATH = pathlib.Path(__file__).resolve().parents[1] / "tools" / "validate-watch-v1-evidence-pair.py"
SPEC = importlib.util.spec_from_file_location("watch_v1_evidence_pair", MODULE_PATH)
validator = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(validator)

REVISION = "a" * 40
CONFIG = "raise-detector-v1;similarity=0.955"


def trace_rows(session_id, label, sample_count=20, step_ms=160):
    rows = []
    for index in range(sample_count):
        rows.append(
            f"{label},{session_id},{index * step_ms},0.1,0.2,9.7"
        )
    return rows


def trial_row(
    session_id,
    label,
    *,
    sample_count=20,
    duration_ms=3200,
):
    return (
        f"{label},{session_id},{duration_ms},{sample_count},false,0.88,"
        f"1.5.2,{REVISION},{CONFIG}"
    )


def write_pair(root, traces, trials):
    trace_path = root / "sensor-traces.csv"
    trial_path = root / "sensor-trials.csv"
    trace_path.write_text(
        "label,session_id,elapsed_ms,x,y,z\n" + "\n".join(traces) + "\n",
        encoding="utf-8",
    )
    trial_path.write_text(
        "label,session_id,duration_ms,sample_count,detector_triggered,max_similarity,"
        "app_version,source_revision,detector_config\n"
        + "\n".join(trials)
        + "\n",
        encoding="utf-8",
    )
    return trace_path, trial_path


class WatchV1EvidencePairTests(unittest.TestCase):
    def test_accepts_exactly_paired_trace_and_trial_sessions(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            trace_path, trial_path = write_pair(
                root,
                trace_rows(1, "mouth_raise") + trace_rows(2, "normal_move"),
                [
                    trial_row(1, "mouth_raise"),
                    trial_row(2, "normal_move"),
                ],
            )

            result = validator.validate_pair(trace_path, trial_path)

            self.assertTrue(result["valid"])
            self.assertEqual(result["paired_session_count"], 2)
            self.assertEqual(result["labels"]["mouth_raise"], 1)
            self.assertEqual(result["labels"]["normal_move"], 1)

    def test_rejects_trace_session_without_trial_outcome(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            trace_path, trial_path = write_pair(
                root,
                trace_rows(1, "mouth_raise") + trace_rows(2, "normal_move"),
                [trial_row(1, "mouth_raise")],
            )

            with self.assertRaisesRegex(validator.PairError, "missing trial outcomes: 2"):
                validator.validate_pair(trace_path, trial_path)

    def test_rejects_trial_outcome_without_trace_session(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            trace_path, trial_path = write_pair(
                root,
                trace_rows(1, "mouth_raise"),
                [
                    trial_row(1, "mouth_raise"),
                    trial_row(2, "normal_move"),
                ],
            )

            with self.assertRaisesRegex(validator.PairError, "missing raw trace sessions: 2"):
                validator.validate_pair(trace_path, trial_path)

    def test_rejects_label_mismatch_for_same_session(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            trace_path, trial_path = write_pair(
                root,
                trace_rows(1, "mouth_raise"),
                [trial_row(1, "normal_move")],
            )

            with self.assertRaisesRegex(validator.PairError, "does not match trial label"):
                validator.validate_pair(trace_path, trial_path)

    def test_rejects_sample_count_mismatch(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            trace_path, trial_path = write_pair(
                root,
                trace_rows(1, "mouth_raise", sample_count=20),
                [trial_row(1, "mouth_raise", sample_count=21)],
            )

            with self.assertRaisesRegex(validator.PairError, "does not match trial sample_count"):
                validator.validate_pair(trace_path, trial_path)

    def test_rejects_trial_duration_shorter_than_latest_trace_sample(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            trace_path, trial_path = write_pair(
                root,
                trace_rows(1, "mouth_raise", sample_count=20, step_ms=160),
                [trial_row(1, "mouth_raise", duration_ms=3000)],
            )

            with self.assertRaisesRegex(validator.PairError, "shorter than latest trace sample"):
                validator.validate_pair(trace_path, trial_path)


if __name__ == "__main__":
    unittest.main()
