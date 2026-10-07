import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WATCH = ROOT / ".github" / "workflows" / "watch-app-test.yml"
PHYSICAL = ROOT / ".github" / "workflows" / "physical-quality-evidence-test.yml"

CHECKOUT_SHA = "3d3c42e5aac5ba805825da76410c181273ba90b1"  # v7.0.1, node24
SETUP_ANDROID_SHA = "be39fa834029ff78f1a44aa3bb0819b8fc2bd8fd"  # v4.0.4, node24
UPLOAD_ARTIFACT_SHA = "043fb46d1a93c77aae656e7c1c64a875d1fc6a0a"  # v7.0.1, node24

EXPECTED = {
    WATCH: [
        ("actions/checkout", CHECKOUT_SHA),
        ("android-actions/setup-android", SETUP_ANDROID_SHA),
        ("actions/upload-artifact", UPLOAD_ARTIFACT_SHA),
        ("actions/upload-artifact", UPLOAD_ARTIFACT_SHA),
    ],
    PHYSICAL: [
        ("actions/checkout", CHECKOUT_SHA),
    ],
}


class QualityWorkflowActionPinningTests(unittest.TestCase):
    def _external_action_refs(self, workflow):
        return re.findall(
            r"^\s*(?:-\s*)?uses:\s*([^@\s]+)@([^\s#]+)",
            workflow.read_text(encoding="utf-8"),
            flags=re.MULTILINE,
        )

    def test_external_actions_match_audited_node24_pins(self):
        for workflow, expected in EXPECTED.items():
            with self.subTest(workflow=workflow.name):
                actual = self._external_action_refs(workflow)
                self.assertEqual(
                    actual,
                    expected,
                    f"{workflow.name} action surface/pins drifted from audited Node 24 releases",
                )
                for action, ref in actual:
                    with self.subTest(workflow=workflow.name, action=action):
                        self.assertRegex(ref, r"^[0-9a-f]{40}$")

    def test_checkout_never_persists_credentials(self):
        for workflow in EXPECTED:
            with self.subTest(workflow=workflow.name):
                lines = workflow.read_text(encoding="utf-8").splitlines()
                checkout_indices = [
                    index
                    for index, line in enumerate(lines)
                    if "uses: actions/checkout@" in line
                ]
                self.assertEqual(len(checkout_indices), 1)
                start = checkout_indices[0]
                following_step = next(
                    (
                        index
                        for index, line in enumerate(lines[start + 1 :], start + 1)
                        if line.startswith("      - ")
                    ),
                    len(lines),
                )
                checkout_step = lines[start:following_step]
                self.assertIn(
                    "          persist-credentials: false",
                    checkout_step,
                    "checkout must not leave GitHub credentials in the worktree",
                )


if __name__ == "__main__":
    unittest.main()
