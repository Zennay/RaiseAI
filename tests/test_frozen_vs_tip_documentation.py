"""Regression lock: repository-tip release is not the frozen Watch acceptance build."""
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]
FROZEN_REVISION = "8f719bb273f9b997848864f342598e7df5f090e5"
FROZEN_DIGEST = "867f2a75260c89d9d92416d407df5dc559a05d99d6f506006003b163ad3e51ce"
FROZEN_RUN = "37241768528"


class FrozenVsTipDocumentationTests(unittest.TestCase):
    def test_tip_readme_heading_matches_version_file(self):
        version = (ROOT / "VERSION.txt").read_text(encoding="utf-8").strip()
        self.assertRegex(version, r"^\d+\.\d+\.\d+$")
        heading = (ROOT / "README.md").read_text(encoding="utf-8").splitlines()[0]
        self.assertEqual(heading, f"# Raise AI v{version} — Galaxy Watch 7")

    def test_frozen_operator_guides_keep_exact_acceptance_identity(self):
        for filename in ("START-HERE.md", "PHYSICAL-ACCEPTANCE.md"):
            with self.subTest(filename=filename):
                text = (ROOT / filename).read_text(encoding="utf-8")
                self.assertIn("v1.5.2", text)
                self.assertIn(FROZEN_REVISION, text)
                self.assertIn(FROZEN_DIGEST, text)
                self.assertIn("frozen", text.lower())

    def test_operator_runbook_does_not_point_to_tip_artifact(self):
        text = (ROOT / "PHYSICAL-ACCEPTANCE.md").read_text(encoding="utf-8")
        self.assertIn(FROZEN_RUN, text)
        self.assertIn("RaiseAI-Watch7-v1.5.2-physical-handoff-" + FROZEN_RUN, text)
        self.assertRegex(text, r"(?i)do not substitute a newer APK")

    def test_start_guide_explicitly_forbids_tip_as_frozen_evidence(self):
        text = (ROOT / "START-HERE.md").read_text(encoding="utf-8")
        self.assertIn("do not build from the repository tip", text.lower())
        self.assertIn("start-frozen-acceptance.command", text)


if __name__ == "__main__":
    unittest.main()
