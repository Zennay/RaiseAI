"""Regression: local physical Watch records cannot be staged accidentally.

Uses Git's effective ignore rules, including nested paths, rather than
checking only the textual presence of patterns.
"""
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

class PhysicalEvidenceIgnoreTests(unittest.TestCase):
    def ignored(self, path):
        result = subprocess.run(
            ["git", "check-ignore", "--no-index", "-q", "--", path],
            cwd=ROOT, capture_output=True, check=False,
        )
        self.assertIn(result.returncode, (0, 1), result.stderr.decode(errors="replace"))
        return result.returncode == 0

    def test_private_operator_and_e2e_evidence_ignored_at_any_depth(self):
        for name in ("operator-observations.json", "watch-e2e-evidence.json"):
            for path in (name, "physical-session/" + name, "nested/physical-session/" + name):
                with self.subTest(path=path):
                    self.assertTrue(self.ignored(path))

    def test_private_recordings_are_not_already_tracked(self):
        result = subprocess.run(
            ["git", "ls-files", "-z"], cwd=ROOT, capture_output=True, check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr.decode(errors="replace"))
        private_names = {"operator-observations.json", "watch-e2e-evidence.json"}
        offenders = [
            raw.decode("utf-8", errors="replace")
            for raw in result.stdout.split(bytes([0])) if raw
            and raw.decode("utf-8", errors="replace").split("/")[-1].lower() in private_names
        ]
        self.assertEqual(offenders, [], "private physical evidence must not be Git-tracked")

    def test_documented_templates_and_public_summary_remain_trackable(self):
        for path in (".env.example", ".env.sample", "quality-result.json"):
            with self.subTest(path=path):
                self.assertFalse(self.ignored(path))

if __name__ == "__main__":
    unittest.main()
