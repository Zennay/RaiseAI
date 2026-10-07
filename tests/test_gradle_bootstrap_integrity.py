from pathlib import Path
import re
import stat
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
GRADLEW = ROOT / "gradlew"
WORKFLOW = ROOT / ".github" / "workflows" / "gradle-bootstrap-integrity.yml"
CHECKOUT_SHA = "3d3c42e5aac5ba805825da76410c181273ba90b1"


def read_contract_text(path: Path) -> str:
    mode = path.lstat().st_mode
    if stat.S_ISLNK(mode):
        raise ValueError(f"{path.name}: contract input must not be a symbolic link")
    if not stat.S_ISREG(mode):
        raise ValueError(f"{path.name}: contract input must be a regular file")
    try:
        return path.read_bytes().decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise ValueError(f"{path.name}: contract input must be valid UTF-8") from exc


class GradleBootstrapIntegrityTest(unittest.TestCase):
    def setUp(self):
        self.script = read_contract_text(GRADLEW)

    def test_contract_reader_rejects_symlink_nonregular_and_invalid_utf8(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            regular = root / "regular.txt"
            regular.write_text("safe\n", encoding="utf-8")
            self.assertEqual(read_contract_text(regular), "safe\n")

            linked = root / "linked.txt"
            linked.symlink_to(regular)
            with self.assertRaisesRegex(ValueError, "must not be a symbolic link"):
                read_contract_text(linked)

            directory = root / "directory.txt"
            directory.mkdir()
            with self.assertRaisesRegex(ValueError, "must be a regular file"):
                read_contract_text(directory)

            invalid = root / "invalid.txt"
            invalid.write_bytes(b"safe\xff")
            with self.assertRaisesRegex(ValueError, "must be valid UTF-8"):
                read_contract_text(invalid)

    def test_pins_full_sha256_for_gradle_distribution(self):
        match = re.search(r'^GRADLE_BIN_SHA256="([0-9a-f]{64})"$', self.script, re.MULTILINE)
        self.assertIsNotNone(match, "gradlew must pin a full lowercase SHA-256 digest")

    def test_verifies_download_before_install(self):
        digest = self.script.index('actual_sha256="$(sha256_file "$ZIP.part")"')
        compare = self.script.index('if [ "$actual_sha256" != "$GRADLE_BIN_SHA256" ]')
        install = self.script.index('mv "$ZIP.part" "$ZIP"')
        unzip = self.script.index('unzip -q "$ZIP" -d "$TOOLS"')
        self.assertLess(digest, compare)
        self.assertLess(compare, install)
        self.assertLess(install, unzip)

    def test_never_falls_back_to_unpinned_system_or_neighbor_gradle(self):
        self.assertNotIn("command -v gradle", self.script)
        self.assertNotRegex(
            self.script,
            r"(?m)^\s*exec\s+gradle(?:\s|$)",
            "gradlew must not bypass the pinned distribution with runner PATH state",
        )
        self.assertNotIn("../RaiseAI-Watch7", self.script)
        self.assertNotIn("../RaiseAI-Watch7 1", self.script)

    def test_cached_distribution_is_bound_to_verified_archive(self):
        archive_gate = self.script.index(
            "if archive_is_verified && distribution_matches_archive; then"
        )
        cached_exec = self.script.index('exec "$DIST/bin/gradle" "$@"', archive_gate)
        self.assertLess(archive_gate, cached_exec)

        for marker in (
            '[ ! -L "$ZIP" ] || return 1',
            '[ "$(sha256_file "$ZIP")" = "$GRADLE_BIN_SHA256" ]',
            '[ ! -L "$DIST" ] || return 1',
            '[ ! -L "$path" ] || return 1',
            'cmp -s <(unzip -p "$ZIP" "$entry") "$path" || return 1',
            'actual_count="$(find "$DIST" -type f -print | wc -l | tr -d \'[:space:]\')"',
            '[ "$actual_count" = "$expected_count" ] || return 1',
            'find "$DIST" ! -type d ! -type f -print -quit',
        ):
            with self.subTest(marker=marker):
                self.assertIn(marker, self.script)

    def test_corrupt_cached_install_is_restored_from_verified_archive(self):
        cache_gate = self.script.index(
            "if archive_is_verified && distribution_matches_archive; then"
        )
        restore_gate = self.script.index("if archive_is_verified; then", cache_gate)
        removal = self.script.index('rm -rf "$DIST"', restore_gate)
        extraction = self.script.index('unzip -q "$ZIP" -d "$TOOLS"', removal)
        post_install_gate = self.script.index(
            "if ! distribution_matches_archive; then", extraction
        )
        final_exec = self.script.index('exec "$DIST/bin/gradle" "$@"', post_install_gate)

        self.assertLess(cache_gate, restore_gate)
        self.assertLess(restore_gate, removal)
        self.assertLess(removal, extraction)
        self.assertLess(extraction, post_install_gate)
        self.assertLess(post_install_gate, final_exec)

    def test_symlinked_tools_root_fails_closed(self):
        guard = 'if [ -L "$TOOLS" ]; then'
        mkdir = 'mkdir -p "$TOOLS"'
        self.assertEqual(self.script.count(guard), 1)
        self.assertLess(self.script.index(guard), self.script.index(mkdir))

    def test_checksum_mismatch_deletes_partial_download_and_fails_closed(self):
        mismatch = self.script.index('if [ "$actual_sha256" != "$GRADLE_BIN_SHA256" ]')
        cleanup = self.script.index('rm -f "$ZIP.part"', mismatch)
        failure = self.script.index('exit 1', mismatch)
        install = self.script.index('mv "$ZIP.part" "$ZIP"')
        self.assertLess(mismatch, cleanup)
        self.assertLess(cleanup, failure)
        self.assertLess(failure, install)


class GradleBootstrapWorkflowContractTest(unittest.TestCase):
    def setUp(self):
        self.workflow = read_contract_text(WORKFLOW)

    def test_checkout_uses_audited_node24_release(self):
        expected = (
            f"uses: actions/checkout@{CHECKOUT_SHA} "
            "# v7.0.1 (node24)"
        )
        self.assertEqual(self.workflow.count(expected), 1)
        self.assertNotIn(
            "actions/checkout@11d5960a326750d5838078e36cf38b85af677262",
            self.workflow,
        )

    def test_checkout_is_exact_head_and_does_not_persist_credentials(self):
        expression = (
            "${{ github.event_name == 'pull_request' && "
            "github.event.pull_request.head.sha || github.sha }}"
        )
        self.assertEqual(self.workflow.count(f"          ref: {expression}"), 1)
        self.assertEqual(
            self.workflow.count("          persist-credentials: false"),
            1,
        )


if __name__ == "__main__":
    unittest.main()
