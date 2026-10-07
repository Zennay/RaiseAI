import pathlib
import subprocess
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
EXPECTED_CRITICAL = {
    "build.gradle.kts",
    "settings.gradle.kts",
    "app/build.gradle.kts",
    "app/src/main/java/nl/zennay/raiseai/GatewayClient.kt",
    "app/src/main/java/nl/zennay/raiseai/MainActivity.kt",
    "app/src/main/java/nl/zennay/raiseai/WatchE2eEvidence.kt",
}


def tracked_kotlin_paths() -> list[str]:
    raw = subprocess.check_output(["git", "ls-files", "-z"], cwd=ROOT)
    return sorted(
        item
        for item in raw.decode("utf-8").split("\0")
        if item and pathlib.PurePosixPath(item).suffix.lower() in {".kt", ".kts"}
    )


def decode_strict_utf8(data: bytes, *, label: str) -> str:
    try:
        return data.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise ValueError(f"{label} must be strict UTF-8") from exc


class KotlinSourceContractTests(unittest.TestCase):
    def test_tracked_kotlin_surface_is_nonempty_and_includes_critical_files(self):
        paths = tracked_kotlin_paths()
        self.assertTrue(paths, "tracked Kotlin discovery must find files")
        self.assertTrue(
            EXPECTED_CRITICAL.issubset(paths),
            f"critical Kotlin/Gradle Kotlin files missing from discovery: "
            f"{sorted(EXPECTED_CRITICAL - set(paths))}",
        )

    def test_every_tracked_kotlin_file_is_regular_strict_utf8_text(self):
        for relative in tracked_kotlin_paths():
            with self.subTest(path=relative):
                path = ROOT / relative
                self.assertFalse(
                    path.is_symlink(),
                    f"{relative} must be a regular repository file, not a symlink",
                )
                self.assertTrue(path.is_file(), f"{relative} must resolve to a regular file")
                text = decode_strict_utf8(path.read_bytes(), label=relative)
                self.assertNotIn(
                    "\x00",
                    text,
                    f"{relative} must not contain NUL bytes in source text",
                )

    def test_strict_decoder_rejects_malformed_utf8(self):
        with self.assertRaisesRegex(ValueError, "fixture.kt must be strict UTF-8"):
            decode_strict_utf8(b"fun main() {\xff}\n", label="fixture.kt")


if __name__ == "__main__":
    unittest.main()
