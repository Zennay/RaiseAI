"""Regression guard: legacy Watch guides must not authorize physical acceptance.

Source-only check; does not claim real-device acceptance.
"""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
LEGACY_GUIDES = {
    "DEVICE-TEST.md": "Historical fallback checklist only",
    "CHATGPT-WEB-SETUP.md": "Legacy fallback setup only",
    "GEMINI-HOME-SETUP.md": "Fallback integration only",
}
CANONICAL_LAUNCHER = "start-frozen-acceptance.command"
CANONICAL_GUIDE = "START-HERE.md"
FROZEN_TAG = "physical-handoff-v1.5.2-8f719bb"


def validate_legacy_guide(name: str, content: str) -> None:
    """Fail closed when an older guide loses its explicit acceptance boundary."""
    if name not in LEGACY_GUIDES:
        raise ValueError("Unrecognized historical guide")
    introduction = "\n".join(content.splitlines()[:8])
    required = (
        LEGACY_GUIDES[name],
        "not the current physical acceptance path"
        if name != "DEVICE-TEST.md" else "Do not use this V0.3 Gemini-first checklist",
        CANONICAL_LAUNCHER,
        CANONICAL_GUIDE,
    )
    for marker in required:
        if marker not in introduction:
            raise ValueError(f"{name}: missing introductory boundary: {marker}")
    if "issue #34" not in introduction and name != "DEVICE-TEST.md":
        raise ValueError(f"{name}: physical gate not identified")


class LegacyGuideAcceptanceBoundaryTests(unittest.TestCase):
    def test_all_historical_guides_have_prominent_boundaries(self):
        for name in LEGACY_GUIDES:
            with self.subTest(name=name):
                validate_legacy_guide(name, (ROOT / name).read_text(encoding="utf-8"))

    def test_missing_legacy_disclaimer_rejected(self):
        name = "GEMINI-HOME-SETUP.md"
        source = (ROOT / name).read_text(encoding="utf-8")
        with self.assertRaises(ValueError):
            validate_legacy_guide(name, source.replace(LEGACY_GUIDES[name], "Current setup", 1))

    def test_missing_canonical_launcher_rejected(self):
        name = "CHATGPT-WEB-SETUP.md"
        source = (ROOT / name).read_text(encoding="utf-8")
        with self.assertRaises(ValueError):
            validate_legacy_guide(name, source.replace(CANONICAL_LAUNCHER, "old-launcher.command", 1))

    def test_disclaimer_buried_after_intro_rejected(self):
        name = "DEVICE-TEST.md"
        source = (ROOT / name).read_text(encoding="utf-8")
        lines = source.splitlines()
        warning = lines.pop(2)
        lines.extend([""] * 12 + [warning])
        with self.assertRaises(ValueError):
            validate_legacy_guide(name, "\n".join(lines))

    def test_unknown_guide_rejected(self):
        with self.assertRaises(ValueError):
            validate_legacy_guide("UNRELATED.md", "anything")


if __name__ == "__main__":
    unittest.main()
