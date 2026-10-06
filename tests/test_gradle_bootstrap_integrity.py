import re
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
GRADLEW = ROOT / "gradlew"


class GradleBootstrapIntegrityTest(unittest.TestCase):
    def setUp(self):
        self.script = GRADLEW.read_text(encoding="utf-8")

    def test_pins_full_sha256_for_gradle_distribution(self):
        match = re.search(r'^GRADLE_BIN_SHA256="([0-9a-f]{64})"$', self.script, re.MULTILINE)
        self.assertIsNotNone(match, "gradlew must pin a full lowercase SHA-256 digest")

    def test_verifies_download_before_install(self):
        digest = self.script.index('actual_sha256="$(sha256sum "$ZIP.part"')
        compare = self.script.index('if [ "$actual_sha256" != "$GRADLE_BIN_SHA256" ]')
        install = self.script.index('mv "$ZIP.part" "$ZIP"')
        unzip = self.script.index('unzip -q "$ZIP" -d "$TOOLS"')
        self.assertLess(digest, compare)
        self.assertLess(compare, install)
        self.assertLess(install, unzip)

    def test_checksum_mismatch_deletes_partial_download_and_fails_closed(self):
        mismatch = self.script.index('if [ "$actual_sha256" != "$GRADLE_BIN_SHA256" ]')
        cleanup = self.script.index('rm -f "$ZIP.part"', mismatch)
        failure = self.script.index('exit 1', mismatch)
        install = self.script.index('mv "$ZIP.part" "$ZIP"')
        self.assertLess(mismatch, cleanup)
        self.assertLess(cleanup, failure)
        self.assertLess(failure, install)


if __name__ == "__main__":
    unittest.main()
