import re
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
GRADLEW = ROOT / "gradlew"
WORKFLOW = ROOT / ".github" / "workflows" / "gradle-bootstrap-integrity.yml"
CHECKOUT_SHA = "3d3c42e5aac5ba805825da76410c181273ba90b1"


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

    def test_never_falls_back_to_unpinned_system_gradle(self):
        self.assertNotIn("command -v gradle", self.script)
        self.assertNotRegex(
            self.script,
            r"(?m)^\s*exec\s+gradle(?:\s|$)",
            "gradlew must not bypass the pinned distribution with runner PATH state",
        )

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
        self.workflow = WORKFLOW.read_text(encoding="utf-8")

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
