"""Regression lock for dynamically versioned Watch CI upload artifacts.

This check is deliberately text-only and does not require PyYAML or a runner.
It guards the release artifact consumer contract without touching Watch builds.
"""
from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "watch-app-test.yml"


class WatchArtifactVersionNameContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.workflow = WORKFLOW.read_text(encoding="utf-8")

    def test_version_is_exported_from_version_file(self):
        self.assertRegex(
            self.workflow,
            r'version="\$\(tr -d [^\n]+ < VERSION\.txt\)"',
        )
        self.assertIn('echo "RAISE_HANDOFF_VERSION=$version" >> "$GITHUB_ENV"', self.workflow)

    def test_both_public_upload_names_use_version_from_environment(self):
        artifact_names = re.findall(
            r"^\s+name:\s+(RaiseAI-Watch7-[^\n]+)$",
            self.workflow,
            re.MULTILINE,
        )
        self.assertEqual(len(artifact_names), 2, artifact_names)
        for name in artifact_names:
            with self.subTest(name=name):
                self.assertIn("v${{ env.RAISE_HANDOFF_VERSION }}", name)
                self.assertIn("${{ github.run_id }}", name)
                self.assertNotRegex(name, r"v\d+\.\d+(?:\.\d+)?")

    def test_main_handoff_is_not_published_on_pull_requests(self):
        self.assertRegex(
            self.workflow,
            r"(?m)^\s+- name: Upload exact main physical handoff\n"
            r"\s+if: github\.event_name == 'push' && github\.ref == 'refs/heads/main'",
        )


if __name__ == "__main__":
    unittest.main()
