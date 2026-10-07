import importlib.util
import os
import pathlib
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

MODULE_PATH = pathlib.Path(__file__).resolve().parents[1] / "analyze-watch-data.py"
SPEC = importlib.util.spec_from_file_location("watch_data_analyzer", MODULE_PATH)
analyzer = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = analyzer
SPEC.loader.exec_module(analyzer)


class WatchDataAnalyzerTests(unittest.TestCase):
    def write_trace(self, content: str | bytes) -> pathlib.Path:
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        path = pathlib.Path(temp.name) / "sensor-traces.csv"
        if isinstance(content, bytes):
            path.write_bytes(content)
        else:
            path.write_text(content, encoding="utf-8")
        return path

    def test_valid_trace_produces_threshold_suggestion(self):
        path = self.write_trace(
            "label,session_id,elapsed_ms,x,y,z\n"
            "mouth_raise,1,0,0,0,9.8\n"
            "mouth_raise,1,100,0,0,9.8\n"
            "view_time,2,0,9.8,0,0\n"
            "view_time,2,100,9.8,0,0\n"
        )

        sessions = analyzer.read_sessions(path)
        output = analyzer.render_analysis(sessions)

        self.assertIn("Good orientation separation detected.", output)
        self.assertIn("Suggested similarityThreshold", output)

    def test_rejects_duplicate_columns(self):
        path = self.write_trace(
            "label,session_id,elapsed_ms,x,y,z,z\n"
            "mouth_raise,1,0,0,0,9.8,9.8\n"
        )
        with self.assertRaisesRegex(analyzer.TraceError, "duplicate columns"):
            analyzer.read_sessions(path)

    def test_rejects_surplus_row_fields(self):
        path = self.write_trace(
            "label,session_id,elapsed_ms,x,y,z\n"
            "mouth_raise,1,0,0,0,9.8,unexpected\n"
        )
        with self.assertRaisesRegex(analyzer.TraceError, "unexpected extra CSV fields"):
            analyzer.read_sessions(path)

    def test_rejects_non_finite_sensor_values(self):
        path = self.write_trace(
            "label,session_id,elapsed_ms,x,y,z\n"
            "mouth_raise,1,0,nan,0,9.8\n"
        )
        with self.assertRaisesRegex(analyzer.TraceError, "x must be finite"):
            analyzer.read_sessions(path)

    def test_rejects_mixed_labels_for_same_session(self):
        path = self.write_trace(
            "label,session_id,elapsed_ms,x,y,z\n"
            "mouth_raise,7,0,0,0,9.8\n"
            "normal_move,7,100,9.8,0,0\n"
        )
        with self.assertRaisesRegex(analyzer.TraceError, "mixes labels"):
            analyzer.read_sessions(path)

    def test_rejects_backwards_elapsed_time(self):
        path = self.write_trace(
            "label,session_id,elapsed_ms,x,y,z\n"
            "mouth_raise,1,100,0,0,9.8\n"
            "mouth_raise,1,50,0,0,9.8\n"
        )
        with self.assertRaisesRegex(analyzer.TraceError, "moved backwards"):
            analyzer.read_sessions(path)

    def test_rejects_invalid_utf8(self):
        path = self.write_trace(
            b"label,session_id,elapsed_ms,x,y,z\n"
            b"mouth_raise,1,0,0,0,9.8\xff\n"
        )
        with self.assertRaisesRegex(analyzer.TraceError, "valid UTF-8"):
            analyzer.read_sessions(path)

    def test_rejects_symlink_input(self):
        with tempfile.TemporaryDirectory() as temp:
            root = pathlib.Path(temp)
            real_path = root / "real.csv"
            real_path.write_text(
                "label,session_id,elapsed_ms,x,y,z\n"
                "mouth_raise,1,0,0,0,9.8\n",
                encoding="utf-8",
            )
            link = root / "linked.csv"
            try:
                link.symlink_to(real_path)
            except (OSError, NotImplementedError):
                self.skipTest("symlinks unavailable")
            with self.assertRaisesRegex(analyzer.TraceError, "must not be a symlink"):
                analyzer.read_sessions(link)

    def test_fifo_input_fails_closed_without_waiting_for_writer(self):
        if not hasattr(os, "mkfifo"):
            self.skipTest("FIFO creation unavailable")
        with tempfile.TemporaryDirectory() as temp:
            fifo = pathlib.Path(temp) / "sensor-traces.csv"
            os.mkfifo(fifo)
            result = subprocess.run(
                [sys.executable, str(MODULE_PATH), str(fifo)],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=2,
            )
            self.assertEqual(result.returncode, 2, result.stderr)
            self.assertIn("not a regular file", result.stderr)

    def test_path_replacement_after_open_cannot_change_parsed_trace(self):
        with tempfile.TemporaryDirectory() as temp:
            root = pathlib.Path(temp)
            path = root / "sensor-traces.csv"
            path.write_text(
                "label,session_id,elapsed_ms,x,y,z\n"
                "mouth_raise,1,0,0,0,9.8\n",
                encoding="utf-8",
            )
            replacement = (
                "label,session_id,elapsed_ms,x,y,z\n"
                "view_time,99,0,9.8,0,0\n"
            )
            real_fstat = analyzer.os.fstat
            swapped = False

            def replace_path_after_open(fd):
                nonlocal swapped
                metadata = real_fstat(fd)
                if not swapped:
                    swapped = True
                    path.unlink()
                    path.write_text(replacement, encoding="utf-8")
                return metadata

            with mock.patch.object(
                analyzer.os,
                "fstat",
                side_effect=replace_path_after_open,
            ):
                sessions = analyzer.read_sessions(path)

            self.assertIn(("mouth_raise", 1), sessions)
            self.assertNotIn(("view_time", 99), sessions)
            self.assertIn(
                "view_time,99",
                path.read_text(encoding="utf-8"),
            )

    def test_degenerate_mouth_reference_fails_closed(self):
        sessions = {
            ("mouth_raise", 1): [analyzer.Sample(0, 0.0, 0.0, 9.8)],
            ("mouth_raise", 2): [analyzer.Sample(0, 0.0, 0.0, -9.8)],
        }
        with self.assertRaisesRegex(analyzer.TraceError, "degenerate reference"):
            analyzer.render_analysis(sessions)


if __name__ == "__main__":
    unittest.main()
