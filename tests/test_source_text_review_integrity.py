import pathlib
import subprocess
import unicodedata
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
TEXT_SUFFIXES = {
    ".cfg",
    ".command",
    ".conf",
    ".css",
    ".gradle",
    ".ini",
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
    ".txt",
    ".xml",
    ".yaml",
    ".yml",
}
EXACT_TEXT_PATHS = {".gitignore", "gradlew", "VERSION.txt"}
ALLOWED_CONTROL_CODEPOINTS = {0x0009, 0x000A}  # horizontal tab and LF
ALLOWED_FORMAT_CODEPOINTS = {0x200C, 0x200D}  # ZWNJ and ZWJ


def is_reviewable_text_path(item: str) -> bool:
    return item in EXACT_TEXT_PATHS or pathlib.PurePosixPath(item).suffix.lower() in TEXT_SUFFIXES

FORBIDDEN_INVISIBLE_CODEPOINTS = {
    0x0085: "NEXT LINE",
    0x00AD: "SOFT HYPHEN",
    0x034F: "COMBINING GRAPHEME JOINER",
    0x061C: "ARABIC LETTER MARK",
    0x180E: "MONGOLIAN VOWEL SEPARATOR",
    0x200B: "ZERO WIDTH SPACE",
    0x200E: "LEFT-TO-RIGHT MARK",
    0x200F: "RIGHT-TO-LEFT MARK",
    0x202A: "LEFT-TO-RIGHT EMBEDDING",
    0x202B: "RIGHT-TO-LEFT EMBEDDING",
    0x202C: "POP DIRECTIONAL FORMATTING",
    0x202D: "LEFT-TO-RIGHT OVERRIDE",
    0x202E: "RIGHT-TO-LEFT OVERRIDE",
    0x2028: "LINE SEPARATOR",
    0x2029: "PARAGRAPH SEPARATOR",
    0x2060: "WORD JOINER",
    0x2066: "LEFT-TO-RIGHT ISOLATE",
    0x2067: "RIGHT-TO-LEFT ISOLATE",
    0x2068: "FIRST STRONG ISOLATE",
    0x2069: "POP DIRECTIONAL ISOLATE",
    0x206A: "INHIBIT SYMMETRIC SWAPPING",
    0x206B: "ACTIVATE SYMMETRIC SWAPPING",
    0x206C: "INHIBIT ARABIC FORM SHAPING",
    0x206D: "ACTIVATE ARABIC FORM SHAPING",
    0x206E: "NATIONAL DIGIT SHAPES",
    0x206F: "NOMINAL DIGIT SHAPES",
    0xFEFF: "ZERO WIDTH NO-BREAK SPACE",
}


def tracked_reviewable_text_paths():
    raw = subprocess.check_output(["git", "ls-files", "-z"], cwd=ROOT)
    return sorted(
        item
        for item in raw.decode("utf-8").split("\0")
        if item and is_reviewable_text_path(item)
    )


def validate_reviewable_text(raw: bytes, relative: str) -> None:
    if b"\r" in raw:
        raise ValueError(
            f"{relative}: source must use LF line endings; carriage returns are forbidden"
        )

    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError(f"{relative}: source must be strict UTF-8") from exc

    if "\x00" in text:
        raise ValueError(f"{relative}: source must not contain NUL characters")

    for index, char in enumerate(text):
        codepoint = ord(char)
        if codepoint in FORBIDDEN_INVISIBLE_CODEPOINTS:
            name = FORBIDDEN_INVISIBLE_CODEPOINTS[codepoint]
            raise ValueError(
                f"{relative}: forbidden invisible control {name} U+{codepoint:04X} "
                f"at character {index}"
            )

        category = unicodedata.category(char)
        if category == "Cc" and codepoint not in ALLOWED_CONTROL_CODEPOINTS:
            raise ValueError(
                f"{relative}: forbidden Unicode control U+{codepoint:04X} "
                f"at character {index}"
            )
        if category == "Cf" and codepoint not in ALLOWED_FORMAT_CODEPOINTS:
            raise ValueError(
                f"{relative}: forbidden Unicode format control U+{codepoint:04X} "
                f"at character {index}"
            )


class SourceTextReviewIntegrityTests(unittest.TestCase):
    def test_common_text_config_extensions_are_reviewable(self):
        for relative in ("notes.txt", "config.ini", "policy.cfg", "service.conf", "nested/README.TXT"):
            with self.subTest(relative=relative):
                self.assertTrue(is_reviewable_text_path(relative))

    def test_unrelated_binary_extensions_are_not_reviewable(self):
        for relative in ("artifact.apk", "image.png", "archive.zip"):
            with self.subTest(relative=relative):
                self.assertFalse(is_reviewable_text_path(relative))

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

    def test_validator_rejects_crlf_and_bare_carriage_returns(self):
        for payload in (b"safe\r\ntail\n", b"safe\rtail\n"):
            with self.subTest(payload=payload):
                with self.assertRaisesRegex(ValueError, "LF line endings"):
                    validate_reviewable_text(payload, "fixture.txt")

    def test_validator_rejects_nul_and_each_forbidden_invisible_control(self):
        with self.assertRaisesRegex(ValueError, "NUL"):
            validate_reviewable_text(b"safe\x00tail", "fixture.py")

        for codepoint, name in FORBIDDEN_INVISIBLE_CODEPOINTS.items():
            with self.subTest(codepoint=f"U+{codepoint:04X}"):
                payload = f"safe {chr(codepoint)} tail".encode("utf-8")
                with self.assertRaisesRegex(ValueError, name):
                    validate_reviewable_text(payload, "fixture.py")

    def test_validator_rejects_non_utf8_bytes(self):
        with self.assertRaisesRegex(ValueError, "strict UTF-8"):
            validate_reviewable_text(b"safe \xff tail", "fixture.py")

    def test_validator_rejects_unlisted_ascii_and_unicode_controls(self):
        cases = (
            ("\\u0007", "Unicode control U+0007"),
            ("\\u0008", "Unicode control U+0008"),
            ("\\u001b", "Unicode control U+001B"),
            ("\\u007f", "Unicode control U+007F"),
            ("\\u009f", "Unicode control U+009F"),
            ("\\u2061", "Unicode format control U+2061"),
            ("\\u2064", "Unicode format control U+2064"),
        )
        for escaped, expected in cases:
            with self.subTest(escaped=escaped):
                value = escaped.encode("ascii").decode("unicode_escape")
                payload = f"safe {value} tail".encode("utf-8")
                with self.assertRaisesRegex(ValueError, expected):
                    validate_reviewable_text(payload, "fixture.py")

    def test_validator_preserves_allowed_source_whitespace(self):
        validate_reviewable_text(b"safe\\ttext\\nnext line\\n", "fixture.py")


    def test_validator_preserves_joiner_controls_used_by_legitimate_text(self):
        validate_reviewable_text("safe \u200c \u200d tail".encode("utf-8"), "fixture.md")


if __name__ == "__main__":
    unittest.main()
