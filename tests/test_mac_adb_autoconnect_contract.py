import os
import pathlib
import re
import subprocess
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "install-mac-adb-autoconnect.command"


class MacAdbAutoconnectContractTests(unittest.TestCase):
    def setUp(self):
        self.script = SCRIPT.read_text(encoding="utf-8")

    def _run(self, *args):
        with tempfile.TemporaryDirectory() as home:
            env = os.environ.copy()
            env["HOME"] = home
            result = subprocess.run(
                ["bash", str(SCRIPT), *args],
                cwd=ROOT,
                env=env,
                text=True,
                capture_output=True,
                timeout=5,
                check=False,
            )
            state_dir = pathlib.Path(home) / ".raiseai"
            return result, state_dir.exists()

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
        cache = self.script.index('printf \'%s\\n\' "$ENDPOINT" > "$ENDPOINT_FILE"', identity)
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


    def test_unknown_argument_fails_closed_before_state_creation(self):
        result, created_state = self._run("--unexpected")
        self.assertEqual(result.returncode, 2)
        self.assertIn("Usage:", result.stderr)
        self.assertFalse(created_state)

    def test_extra_arguments_fail_closed_before_state_creation(self):
        result, created_state = self._run("--quiet", "extra")
        self.assertEqual(result.returncode, 2)
        self.assertIn("Usage:", result.stderr)
        self.assertFalse(created_state)

    def test_default_non_macos_path_remains_side_effect_free(self):
        result, created_state = self._run()
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout.strip(), "macOS only.")
        self.assertEqual(result.stderr, "")
        self.assertFalse(created_state)

    def test_quiet_non_macos_path_remains_silent_and_side_effect_free(self):
        result, created_state = self._run("--quiet")
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "")
        self.assertEqual(result.stderr, "")
        self.assertFalse(created_state)

    def test_quiet_is_the_only_supported_option(self):
        self.assertIn('case "${1:-}" in', self.script)
        self.assertIn('--quiet)', self.script)
        self.assertIn('exit 2', self.script)

    def test_installed_marker_is_written_only_after_optional_key_backup(self):
        backup_start = self.script.index('if [ -f "$HOME/.android/adbkey" ]; then')
        backup_copy = self.script.index('cp -p "$HOME/.android/adbkey"')
        backup_end = self.script.index('\nfi\n\ntouch "$STATE_DIR/autoconnect-installed"', backup_start)
        marker = self.script.index('touch "$STATE_DIR/autoconnect-installed"')
        self.assertLess(backup_start, backup_copy)
        self.assertLess(backup_copy, backup_end)
        self.assertGreater(marker, backup_end)


if __name__ == "__main__":
    unittest.main()
