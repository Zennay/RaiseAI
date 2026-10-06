import os
import pathlib
import subprocess
import tempfile
import textwrap
import unittest


class PullWatchDataPairingTests(unittest.TestCase):
    def setUp(self):
        self.repo = pathlib.Path(__file__).resolve().parents[1]

    def test_required_trial_gate_rejects_mismatched_trace_and_trial_pair(self):
        trace_rows = "\n".join(
            f"mouth_raise,1,{index * 160},0.1,0.2,9.7"
            for index in range(20)
        )
        trace_csv = "label,session_id,elapsed_ms,x,y,z\n" + trace_rows
        trial_csv = (
            "label,session_id,duration_ms,sample_count,detector_triggered,max_similarity,"
            "app_version,source_revision,detector_config\n"
            "normal_move,1,3200,20,false,0.88,1.5.2,"
            + ("a" * 40)
            + ",raise-detector-v1;similarity=0.955"
        )

        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            fake_bin = root / "bin"
            fake_bin.mkdir()
            output_dir = root / "evidence"
            output_dir.mkdir()
            adb = fake_bin / "adb"
            adb.write_text(
                textwrap.dedent(
                    f"""\
                    #!/bin/bash
                    set -euo pipefail
                    case "$*" in
                      "devices")
                        printf 'List of devices attached\\nwatch-1\\tdevice\\n'
                        ;;
                      "-s watch-1 shell getprop ro.build.characteristics")
                        echo "watch"
                        ;;
                      "-s watch-1 shell pm list features")
                        echo "feature:android.hardware.type.watch"
                        ;;
                      "-s watch-1 shell run-as nl.zennay.raiseai cat files/sensor-traces.csv")
                        cat <<'EOF'
                    {trace_csv}
                    EOF
                        ;;
                      "-s watch-1 shell run-as nl.zennay.raiseai cat files/sensor-trials.csv")
                        cat <<'EOF'
                    {trial_csv}
                    EOF
                        ;;
                      *)
                        echo "unexpected fake adb invocation: $*" >&2
                        exit 64
                        ;;
                    esac
                    """
                ),
                encoding="utf-8",
            )
            adb.chmod(0o755)

            env = os.environ.copy()
            env["PATH"] = str(fake_bin) + os.pathsep + env["PATH"]
            env["ANDROID_SERIAL"] = "watch-1"
            env["RAISE_OUTPUT_DIR"] = str(output_dir)
            env["RAISE_REQUIRE_V1_TRIAL_GATE"] = "1"

            completed = subprocess.run(
                ["bash", str(self.repo / "pull-watch-data.command")],
                cwd=self.repo,
                env=env,
                text=True,
                capture_output=True,
                check=False,
            )

            combined = completed.stdout + completed.stderr
            self.assertNotEqual(completed.returncode, 0)
            self.assertIn("V1 trace/trial pairing:", combined)
            self.assertIn("does not match trial label", combined)


if __name__ == "__main__":
    unittest.main()
