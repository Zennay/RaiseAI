from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]
VERSION_RE = re.compile(r"^\d+\.\d+\.\d+$")


class ReleaseDocumentationIdentityContractTests(unittest.TestCase):
    def test_readme_tracks_repository_version(self):
        version = (ROOT / "VERSION.txt").read_text(encoding="utf-8").strip()
        self.assertRegex(version, VERSION_RE)

        first_line = (ROOT / "README.md").read_text(encoding="utf-8").splitlines()[0]
        self.assertEqual(first_line, f"# Raise AI v{version} — Galaxy Watch 7")

    def test_start_here_distinguishes_tip_from_frozen_acceptance(self):
        text = (ROOT / "START-HERE.md").read_text(encoding="utf-8")
        self.assertTrue(
            text.startswith("# Raise AI — START HERE (frozen v1.5.2 acceptance)\n"),
            "START-HERE must identify itself as the frozen acceptance guide, not the repository-tip release",
        )
        required = (
            "The only valid acceptance input is the preserved v1.5.2 handoff",
            "8f719bb273f9b997848864f342598e7df5f090e5",
            "do not build from the repository tip",
            "Do not run `physical-validation.command all` from the current checkout",
        )
        for marker in required:
            with self.subTest(marker=marker):
                self.assertIn(marker, text)

    def test_frozen_acceptance_version_is_not_derived_from_version_txt(self):
        current_version = (ROOT / "VERSION.txt").read_text(encoding="utf-8").strip()
        self.assertNotEqual(
            current_version,
            "1.5.2",
            "This regression is useful only while repository tip differs from the frozen v1.5.2 acceptance input",
        )


if __name__ == "__main__":
    unittest.main()
