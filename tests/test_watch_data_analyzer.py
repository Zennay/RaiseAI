import importlib.util
import os
import pathlib
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "analyze-watch-data.py"
WORKFLOW_PATH = ROOT / ".github" / "workflows" / "watch-data-analyzer-quality.yml"
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
        with self.assertRaisesRegex(analyzer.TraceError, "increase strictly"):
            analyzer.read_sessions(path)

    def test_rejects_duplicate_elapsed_time(self):
        path = self.write_trace(
            "label,session_id,elapsed_ms,x,y,z\n"
            "mouth_raise,1,100,0,0,9.8\n"
            "mouth_raise,1,100,0,0,9.8\n"
        )
        with self.assertRaisesRegex(analyzer.TraceError, "increase strictly"):
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


class WatchDataAnalyzerWorkflowContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.workflow = WORKFLOW_PATH.read_text(encoding="utf-8")

    def test_workflow_is_read_only_exact_head_and_runner_bound(self):
        self.assertIn("permissions:\n  contents: read", self.workflow)
        self.assertIn(
            "    runs-on: [self-hosted, linux, x64, vps-bb300bba]",
            self.workflow,
        )
        self.assertIn('      PYTHONDONTWRITEBYTECODE: "1"', self.workflow)
        self.assertIn(
            "uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1",
            self.workflow,
        )
        exact_head = "${{ github.event_name == 'pull_request' && github.event.pull_request.head.sha || github.sha }}"
        self.assertEqual(self.workflow.count(f"          ref: {exact_head}"), 1)
        self.assertEqual(self.workflow.count(f"          EXPECTED_SHA: {exact_head}"), 1)
        self.assertIn("          persist-credentials: false", self.workflow)
        self.assertIn(
            '          test "$(hostname)" = "vps-bb300bba"',
            self.workflow,
        )
        self.assertIn(
            '          test "$(git rev-parse HEAD)" = "$EXPECTED_SHA"',
            self.workflow,
        )
        self.assertNotIn("pull_request_target:", self.workflow)
        self.assertNotIn("secrets.", self.workflow)
        self.assertNotIn("continue-on-error: true", self.workflow)

    def test_workflow_run_steps_are_strict_and_leave_clean_worktree(self):
        self.assertEqual(self.workflow.count("        shell: bash"), 3)
        self.assertEqual(self.workflow.count("        run: |"), 3)
        self.assertEqual(self.workflow.count("          set -euo pipefail"), 3)
        for command in (
            "          python3 -m py_compile analyze-watch-data.py",
            "          python3 -m unittest tests/test_watch_data_analyzer.py -v",
            "          git diff --exit-code -- .",
            "          git diff --cached --exit-code -- .",
            '          test -z "$(git ls-files --others --exclude-standard)"',
        ):
            with self.subTest(command=command):
                self.assertIn(command, self.workflow)

    def test_workflow_triggers_on_every_owned_input(self):
        for path in (
            "analyze-watch-data.py",
            "tests/test_watch_data_analyzer.py",
            ".github/workflows/watch-data-analyzer-quality.yml",
        ):
            with self.subTest(path=path):
                self.assertEqual(
                    self.workflow.count(f'      - "{path}"'),
                    2,
                    f"{path} must trigger both push and pull_request validation",
                )


if __name__ == "__main__":
    unittest.main()
