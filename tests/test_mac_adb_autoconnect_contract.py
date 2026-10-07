import pathlib
import re
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "install-mac-adb-autoconnect.command"


class MacAdbAutoconnectContractTests(unittest.TestCase):
    def setUp(self):
        self.script = SCRIPT.read_text(encoding="utf-8")

    def test_accepts_both_canonical_galaxy_watch_7_model_spellings(self):
        self.assertIn("SM-L315F|SM_L315F)", self.script)

    def test_watch_model_matcher_is_exact_not_substring_based(self):
        self.assertRegex(
            self.script,
            re.compile(
                r'case "\$model" in\n'
                r'\s+SM-L315F\|SM_L315F\)\n'
                r'\s+printf',
                re.MULTILINE,
            ),
        )
        self.assertNotIn('grep -qi "SM', self.script)

    def test_autoconnect_helper_only_caches_endpoint_after_watch_match(self):
        match = self.script.index('TARGET="$(find_watch)"')
        cache = self.script.index('printf \'%s\\n\' "$ENDPOINT" > "$ENDPOINT_FILE"')
        self.assertLess(match, cache)


if __name__ == "__main__":
    unittest.main()
