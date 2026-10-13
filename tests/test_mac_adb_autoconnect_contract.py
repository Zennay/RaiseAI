import pathlib
import re
import stat
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "install-mac-adb-autoconnect.command"


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


class MacAdbAutoconnectContractTests(unittest.TestCase):
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

    def test_accepts_both_canonical_galaxy_watch_7_model_spellings(self):
        self.assertIn("SM-L315F|SM_L315F)", self.script)

    def test_expected_watch_requires_model_and_watch_characteristics(self):
        matcher = self.script[
            self.script.index("is_expected_watch() {"):
            self.script.index("find_watch() {")
        ]
        self.assertIn("ro.product.model", matcher)
        self.assertIn("ro.build.characteristics", matcher)
        self.assertIn("SM-L315F|SM_L315F)", matcher)
        self.assertIn("grep -qi 'watch'", matcher)

    def test_generated_helper_body_uses_literal_heredoc(self):
        self.assertIn("cat <<'HELPER_EOF'", self.script)
        self.assertNotIn('cat > "$HELPER" <<EOF', self.script)
        self.assertIn("printf 'ADB=%q\\n' \"$ADB\"", self.script)
        self.assertIn("printf 'STATE_DIR=%q\\n' \"$STATE_DIR\"", self.script)
        self.assertIn("printf 'ENDPOINT_FILE=%q\\n' \"$ENDPOINT_FILE\"", self.script)

    def test_cached_endpoint_must_itself_be_expected_watch(self):
        cached = self.script.index('CACHED="$(tr -d')
        checked = self.script.index('if is_expected_watch "$CACHED"; then', cached)
        exit_ok = self.script.index('exit 0', checked)
        mdns = self.script.index('while IFS= read -r ENDPOINT', cached)

        self.assertLess(cached, checked)
        self.assertLess(checked, exit_ok)
        self.assertLess(exit_ok, mdns)

    def test_mdns_tries_each_endpoint_and_only_caches_matching_watch(self):
        loop = self.script.index('while IFS= read -r ENDPOINT')
        connect = self.script.index('"$ADB" connect "$ENDPOINT"', loop)
        identity = self.script.index('if is_expected_watch "$ENDPOINT"; then', connect)
        cache = self.script.index("printf '%s\\n' \"$ENDPOINT\" > \"$ENDPOINT_FILE\"", identity)
        source = self.script.index("awk '/_adb-tls-connect[.]_tcp/ {print $3}'", loop)

        self.assertLess(loop, connect)
        self.assertLess(connect, identity)
        self.assertLess(identity, cache)
        self.assertLess(cache, source)
        self.assertNotIn("{print $3; exit}", self.script)

    def test_existing_connected_watch_is_checked_before_reconnect_attempts(self):
        target = self.script.index('TARGET="$(find_watch)"')
        cached = self.script.index('if [ -f "$ENDPOINT_FILE" ]')
        mdns = self.script.index('while IFS= read -r ENDPOINT')

        self.assertLess(target, cached)
        self.assertLess(cached, mdns)

    def test_status_message_uses_raise_ai_name(self):
        self.assertIn('echo "Raise AI ADB auto-connect installed."', self.script)
        self.assertNotIn('echo "Race AI ADB auto-connect installed."', self.script)


if __name__ == "__main__":
    unittest.main()
