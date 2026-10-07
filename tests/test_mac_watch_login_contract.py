import pathlib
import re
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "login-from-mac.command"


class MacWatchLoginContractTests(unittest.TestCase):
    def setUp(self):
        self.script = SCRIPT.read_text(encoding="utf-8")

    def test_targets_only_canonical_galaxy_watch_7_model_aliases(self):
        self.assertIn("SM-L315F|SM_L315F)", self.script)
        self.assertIn("ro.build.characteristics", self.script)
        self.assertIn("ro.product.model", self.script)

    def test_collects_candidates_instead_of_silently_taking_first_watch(self):
        self.assertIn('WATCHES=()', self.script)
        self.assertIn('WATCHES+=("$serial")', self.script)
        selection = self.script.index('case "${#WATCHES[@]}" in')
        launch = self.script.index('shell am start')
        self.assertLess(selection, launch)

    def test_zero_and_multiple_watch_targets_fail_before_login_launch(self):
        selection = self.script.index('case "${#WATCHES[@]}" in')
        block = self.script[selection:self.script.index('echo "Watch gevonden:', selection)]
        self.assertRegex(block, re.compile(r"\n\s*0\).*?exit 1", re.DOTALL))
        self.assertRegex(block, re.compile(r"\n\s*\*\).*?exit 1", re.DOTALL))
        self.assertIn("Verbind precies één Watch", block)


if __name__ == "__main__":
    unittest.main()
