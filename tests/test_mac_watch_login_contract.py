import pathlib
import re
import stat
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "login-from-mac.command"


def read_script_text(path: pathlib.Path) -> str:
    mode = path.lstat().st_mode
    if stat.S_ISLNK(mode):
        raise ValueError(f"{path.name}: script input must not be a symbolic link")
    if not stat.S_ISREG(mode):
        raise ValueError(f"{path.name}: script input must be a regular file")
    try:
        return path.read_bytes().decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise ValueError(f"{path.name}: script input must be valid UTF-8") from exc


class MacWatchLoginContractTests(unittest.TestCase):
    def setUp(self):
        self.script = read_script_text(SCRIPT)

    def test_script_reader_rejects_symlink_nonregular_and_invalid_utf8(self):
        with tempfile.TemporaryDirectory() as temp:
            root = pathlib.Path(temp)
            regular = root / "regular.command"
            regular.write_text("#!/bin/bash\n", encoding="utf-8")
            self.assertEqual(read_script_text(regular), "#!/bin/bash\n")

            linked = root / "linked.command"
            linked.symlink_to(regular)
            with self.assertRaisesRegex(ValueError, "must not be a symbolic link"):
                read_script_text(linked)

            directory = root / "directory.command"
            directory.mkdir()
            with self.assertRaisesRegex(ValueError, "must be a regular file"):
                read_script_text(directory)

            invalid = root / "invalid.command"
            invalid.write_bytes(b"#!/bin/bash\n\xff")
            with self.assertRaisesRegex(ValueError, "must be valid UTF-8"):
                read_script_text(invalid)

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
