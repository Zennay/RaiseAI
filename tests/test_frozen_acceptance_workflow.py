import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "frozen-acceptance-tooling-test.yml"
CHECKOUT_SHA = "3d3c42e5aac5ba805825da76410c181273ba90b1"


class FrozenAcceptanceWorkflowContractTests(unittest.TestCase):
    def setUp(self):
        self.text = WORKFLOW.read_text(encoding="utf-8")

    def test_checkout_uses_audited_node24_release(self):
        expected = (
            f"uses: actions/checkout@{CHECKOUT_SHA} "
            "# v7.0.1 (node24)"
        )
        self.assertEqual(self.text.count(expected), 1)
        self.assertNotIn(
            "actions/checkout@11d5960a326750d5838078e36cf38b85af677262",
            self.text,
        )

    def test_checkout_is_exact_head_and_credentials_are_ephemeral(self):
        expression = (
            "${{ github.event_name == 'pull_request' && "
            "github.event.pull_request.head.sha || github.sha }}"
        )
        self.assertEqual(self.text.count(f"          ref: {expression}"), 1)
        self.assertEqual(
            self.text.count("          persist-credentials: false"),
            1,
        )

    def test_workflow_contract_test_is_self_gating(self):
        self.assertEqual(
            self.text.count(
                '      - "tests/test_frozen_acceptance_workflow.py"'
            ),
            2,
        )
        self.assertIn(
            "python3 -m unittest discover -s tests "
            "-p 'test_frozen_acceptance_workflow.py'",
            self.text,
        )


if __name__ == "__main__":
    unittest.main()
