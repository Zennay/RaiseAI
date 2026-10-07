import pathlib
import subprocess
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
TEXT_SUFFIXES = {
    ".command",
    ".css",
    ".gradle",
    ".js",
    ".json",
    ".kt",
    ".kts",
    ".md",
    ".mjs",
    ".cjs",
    ".properties",
    ".pro",
    ".ps1",
    ".py",
    ".service",
    ".sh",
    ".toml",
    ".xml",
    ".yaml",
    ".yml",
}
EXACT_TEXT_PATHS = {".gitignore", "gradlew", "VERSION.txt"}
FORBIDDEN_BIDI_CODEPOINTS = {
    0x202A: "LEFT-TO-RIGHT EMBEDDING",
    0x202B: "RIGHT-TO-LEFT EMBEDDING",
    0x202C: "POP DIRECTIONAL FORMATTING",
    0x202D: "LEFT-TO-RIGHT OVERRIDE",
    0x202E: "RIGHT-TO-LEFT OVERRIDE",
    0x2066: "LEFT-TO-RIGHT ISOLATE",
    0x2067: "RIGHT-TO-LEFT ISOLATE",
    0x2068: "FIRST STRONG ISOLATE",
    0x2069: "POP DIRECTIONAL ISOLATE",
}


def tracked_reviewable_text_paths():
    raw = subprocess.check_output(["git", "ls-files", "-z"], cwd=ROOT)
    return sorted(
        item
        for item in raw.decode("utf-8").split("\0")
        if item
        and (
            item in EXACT_TEXT_PATHS
            or pathlib.PurePosixPath(item).suffix.lower() in TEXT_SUFFIXES
        )
    )


def validate_reviewable_text(raw: bytes, relative: str) -> None:
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError(f"{relative}: source must be strict UTF-8") from exc

    if "\x00" in text:
        raise ValueError(f"{relative}: source must not contain NUL characters")

    for index, char in enumerate(text):
        codepoint = ord(char)
        if codepoint in FORBIDDEN_BIDI_CODEPOINTS:
            name = FORBIDDEN_BIDI_CODEPOINTS[codepoint]
            raise ValueError(
                f"{relative}: forbidden bidi control {name} U+{codepoint:04X} at character {index}"
            )


class SourceTextReviewIntegrityTests(unittest.TestCase):
    def test_reviewable_text_surface_is_nonempty_and_covers_critical_sources(self):
        paths = tracked_reviewable_text_paths()
        self.assertTrue(paths, "review-integrity discovery must find tracked text sources")
        for critical in (
            "app/src/main/java/nl/zennay/raiseai/MainActivity.kt",
            "app/src/main/assets/raiseai_wear/wear.js",
            "app/src/main/assets/raiseai_wear/wear.css",
            "app/src/main/AndroidManifest.xml",
            "gateway/src/server.mjs",
            "physical-validation.command",
            "gradle.properties",
            "app/proguard-rules.pro",
            "gateway/deploy/raise-gateway.service",
            ".gitignore",
            "VERSION.txt",
            "PHYSICAL-ACCEPTANCE.md",
        ):
            with self.subTest(critical=critical):
                self.assertIn(critical, paths)

    def test_every_tracked_reviewable_text_file_is_regular_utf8_and_unambiguous(self):
        for relative in tracked_reviewable_text_paths():
            with self.subTest(path=relative):
                path = ROOT / relative
                self.assertFalse(
                    path.is_symlink(),
                    f"{relative} must not use symlink indirection",
                )
                self.assertTrue(path.is_file(), f"{relative} must be a regular file")
                validate_reviewable_text(path.read_bytes(), relative)

    def test_validator_rejects_nul_and_each_bidi_control(self):
        with self.assertRaisesRegex(ValueError, "NUL"):
            validate_reviewable_text(b"safe\x00tail", "fixture.py")

        for codepoint, name in FORBIDDEN_BIDI_CODEPOINTS.items():
            with self.subTest(codepoint=f"U+{codepoint:04X}"):
                payload = f"safe {chr(codepoint)} tail".encode("utf-8")
                with self.assertRaisesRegex(ValueError, name):
                    validate_reviewable_text(payload, "fixture.py")

    def test_validator_rejects_non_utf8_bytes(self):
        with self.assertRaisesRegex(ValueError, "strict UTF-8"):
            validate_reviewable_text(b"safe \xff tail", "fixture.py")


if __name__ == "__main__":
    unittest.main()
