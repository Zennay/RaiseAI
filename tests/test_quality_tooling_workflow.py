import pathlib
import re
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "quality-tooling-test.yml"

ADB_CONTRACT_INPUTS = (
    "pull-diagnostics.command",
    "pull-watch-data.command",
    "install-watch-apk.command",
    "provision-watch-gateway.command",
    "physical-validation.command",
    "tests/test_adb_device_binding.py",
)

SELF_CONTRACT_INPUTS = (
    "tests/test_quality_tooling_workflow.py",
    ".github/workflows/quality-tooling-test.yml",
)


class QualityToolingWorkflowContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = WORKFLOW.read_text(encoding="utf-8")

    def test_adb_contract_inputs_trigger_push_and_pull_request(self):
        for path in ADB_CONTRACT_INPUTS:
            with self.subTest(path=path):
                self.assertEqual(
                    self.source.count(f'- "{path}"'),
                    2,
                    f"{path} must trigger both push and pull_request quality runs",
                )

    def test_workflow_contract_changes_trigger_and_run_themselves(self):
        for path in SELF_CONTRACT_INPUTS:
            with self.subTest(path=path):
                self.assertEqual(self.source.count(f'- "{path}"'), 2)
        self.assertIn("tests.test_quality_tooling_workflow", self.source)

    def test_checkout_is_immutable_and_does_not_persist_credentials(self):
        self.assertRegex(
            self.source,
            re.compile(r"uses: actions/checkout@[0-9a-f]{40}(?:\\s+#.*)?$",
                       re.MULTILINE),
        )
        self.assertNotIn("uses: actions/checkout@v", self.source)
        self.assertIn("persist-credentials: false", self.source)
        self.assertIn("permissions:\n  contents: read", self.source)


if __name__ == "__main__":
    unittest.main()
