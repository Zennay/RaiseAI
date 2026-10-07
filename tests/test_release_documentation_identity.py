from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]
VERSION_RE = re.compile(r"^\d+\.\d+\.\d+$")
FROZEN_SOURCE_REVISION = "8f719bb273f9b997848864f342598e7df5f090e5"
FROZEN_RELEASE_TAG = "physical-handoff-v1.5.2-8f719bb"
FROZEN_RELEASE_ASSET_ID = "611084738"
FROZEN_ARCHIVE_SHA256 = "867f2a75260c89d9d92416d407df5dc559a05d99d6f506006003b163ad3e51ce"


class ReleaseDocumentationIdentityContractTests(unittest.TestCase):
    def test_readme_tracks_repository_version(self):
        version = (ROOT / "VERSION.txt").read_text(encoding="utf-8").strip()
        self.assertRegex(version, VERSION_RE)

        first_line = (ROOT / "README.md").read_text(encoding="utf-8").splitlines()[0]
        self.assertEqual(first_line, f"# Raise AI v{version} — Galaxy Watch 7")

    def test_readme_next_gate_pins_exact_preserved_carrier_identity(self):
        text = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertEqual(text.count("## Next proof gate\n"), 1)
        next_gate = text.split("## Next proof gate\n", 1)[1].split("\n## ", 1)[0]
        required = (
            f"merged-main revision `{FROZEN_SOURCE_REVISION}`",
            f"GitHub Release tag `{FROZEN_RELEASE_TAG}`",
            f"Release asset id `{FROZEN_RELEASE_ASSET_ID}`",
            f"archive digest `sha256:{FROZEN_ARCHIVE_SHA256}`",
            "Any different carrier or rebuilt APK is not acceptance evidence.",
        )
        for marker in required:
            with self.subTest(marker=marker):
                self.assertEqual(
                    next_gate.count(marker),
                    1,
                    "README next proof gate must bind the frozen carrier unambiguously",
                )

    def test_start_here_distinguishes_tip_from_frozen_acceptance(self):
        text = (ROOT / "START-HERE.md").read_text(encoding="utf-8")
        self.assertTrue(
            text.startswith("# Raise AI — START HERE (frozen v1.5.2 acceptance)\n"),
            "START-HERE must identify itself as the frozen acceptance guide, not the repository-tip release",
        )
        required = (
            "The only valid acceptance input is the preserved v1.5.2 handoff",
            FROZEN_SOURCE_REVISION,
            "do not build from the repository tip",
            "Do not run `physical-validation.command all` from the current checkout",
        )
        for marker in required:
            with self.subTest(marker=marker):
                self.assertIn(marker, text)

    def test_start_here_pins_exact_preserved_carrier_identity(self):
        text = (ROOT / "START-HERE.md").read_text(encoding="utf-8")
        required = (
            f"merged-main revision `{FROZEN_SOURCE_REVISION}`",
            f"GitHub Release tag `{FROZEN_RELEASE_TAG}`",
            f"Release asset id `{FROZEN_RELEASE_ASSET_ID}`",
            f"archive digest `sha256:{FROZEN_ARCHIVE_SHA256}`",
        )
        for marker in required:
            with self.subTest(marker=marker):
                self.assertEqual(
                    text.count(marker),
                    1,
                    "START-HERE must bind the frozen acceptance carrier unambiguously",
                )

    def test_operator_guides_pin_the_same_frozen_carrier(self):
        guides = {
            "START-HERE.md": (ROOT / "START-HERE.md").read_text(encoding="utf-8"),
            "PHYSICAL-ACCEPTANCE.md": (ROOT / "PHYSICAL-ACCEPTANCE.md").read_text(encoding="utf-8"),
            "DEVICE-TEST.md": (ROOT / "DEVICE-TEST.md").read_text(encoding="utf-8"),
        }
        markers = (
            FROZEN_SOURCE_REVISION,
            FROZEN_RELEASE_TAG,
            FROZEN_RELEASE_ASSET_ID,
            FROZEN_ARCHIVE_SHA256,
        )
        for guide, text in guides.items():
            for marker in markers:
                with self.subTest(guide=guide, marker=marker):
                    self.assertIn(
                        marker,
                        text,
                        f"{guide} must retain the canonical frozen carrier identity",
                    )

    def test_historical_device_checklist_cannot_masquerade_as_acceptance(self):
        text = (ROOT / "DEVICE-TEST.md").read_text(encoding="utf-8")
        required = (
            "**Historical fallback checklist only.**",
            "Do not use this V0.3 Gemini-first checklist for the current physical acceptance gate.",
            "The only valid acceptance carrier is the preserved Raise AI v1.5.2 handoff",
            "bash ./start-frozen-acceptance.command [gateway-profile]",
            "Any different carrier or rebuilt APK is not acceptance evidence.",
        )
        for marker in required:
            with self.subTest(marker=marker):
                self.assertEqual(
                    text.count(marker),
                    1,
                    "legacy checklist must fail closed toward the canonical frozen acceptance path",
                )

    def test_legacy_fallback_guides_redirect_without_partial_carrier_identity(self):
        guides = {
            "REMOTE-LOGIN.md": (ROOT / "REMOTE-LOGIN.md").read_text(encoding="utf-8"),
            "GEMINI-HOME-SETUP.md": (ROOT / "GEMINI-HOME-SETUP.md").read_text(encoding="utf-8"),
            "CHATGPT-WEB-SETUP.md": (ROOT / "CHATGPT-WEB-SETUP.md").read_text(encoding="utf-8"),
        }
        required = (
            "GitHub issue #34",
            "bash ./start-frozen-acceptance.command [gateway-profile]",
            "START-HERE.md",
        )
        forbidden = (
            FROZEN_SOURCE_REVISION,
            FROZEN_RELEASE_TAG,
            FROZEN_RELEASE_ASSET_ID,
            FROZEN_ARCHIVE_SHA256,
        )
        for guide, text in guides.items():
            for marker in required:
                with self.subTest(guide=guide, required=marker):
                    self.assertIn(
                        marker,
                        text,
                        f"{guide} must redirect operators to the canonical frozen acceptance path",
                    )
            for marker in forbidden:
                with self.subTest(guide=guide, forbidden=marker):
                    self.assertNotIn(
                        marker,
                        text,
                        f"{guide} must not duplicate a partial frozen carrier identity; START-HERE.md is canonical",
                    )

    def test_frozen_acceptance_version_is_not_derived_from_version_txt(self):
        current_version = (ROOT / "VERSION.txt").read_text(encoding="utf-8").strip()
        self.assertNotEqual(
            current_version,
            "1.5.2",
            "This regression is useful only while repository tip differs from the frozen v1.5.2 acceptance input",
        )


if __name__ == "__main__":
    unittest.main()
