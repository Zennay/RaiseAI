import pathlib
import re
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "quality-tooling-test.yml"
COMMAND_ENTRYPOINTS = [
    "pull-diagnostics.command",
    "pull-watch-data.command",
    "install-watch-apk.command",
    "provision-watch-gateway.command",
    "physical-validation.command",
    "start-frozen-acceptance.command",
]


class QualityToolingWorkflowContractTests(unittest.TestCase):
    def setUp(self):
        self.text = WORKFLOW.read_text(encoding="utf-8")

    def test_uses_immutable_checkout_without_persisted_credentials(self):
        self.assertRegex(
            self.text,
            r"uses: actions/checkout@[0-9a-f]{40}(?:\s+#.*)?",
        )
        self.assertIn("persist-credentials: false", self.text)
        self.assertNotIn("actions/checkout@v", self.text)
        self.assertNotIn("pull_request_target:", self.text)

    def test_verifies_exact_requested_revision(self):
        expression = (
            "${{ github.event_name == 'pull_request' && "
            "github.event.pull_request.head.sha || github.sha }}"
        )
        self.assertGreaterEqual(self.text.count(expression), 2)
        self.assertIn('test "$(git rev-parse HEAD)" = "$EXPECTED_SHA"', self.text)

    def test_push_and_pull_request_filters_cover_quality_surface(self):
        paths = [
            *COMMAND_ENTRYPOINTS,
            "tools/analyze-watch-sensor-traces.py",
            "tools/analyze-watch-sensor-trials.py",
            "tools/create-physical-observation-template.py",
            "tools/fetch-frozen-physical-handoff.py",
            "tools/validate-physical-observations.py",
            "tools/validate-watch-e2e-evidence.py",
            "tools/verify-watch-apk-identity.py",
            "tests/test_adb_device_binding.py",
            "tests/test_frozen_acceptance_launcher.py",
            "tests/test_frozen_physical_handoff_fetcher.py",
            "tests/test_physical_observation_template.py",
            "tests/test_physical_observation_validator.py",
            "tests/test_quality_tooling_workflow.py",
            "tests/test_watch_apk_identity.py",
            "tests/test_watch_e2e_evidence_validator.py",
            "tests/test_watch_sensor_trace_analyzer.py",
            "tests/test_watch_sensor_trial_analyzer.py",
            ".github/workflows/quality-tooling-test.yml",
        ]
        for path in paths:
            with self.subTest(path=path):
                self.assertEqual(
                    self.text.count(f'      - "{path}"'),
                    2,
                    f"{path} must trigger both push and pull_request quality CI",
                )

    def test_checks_shell_syntax_for_all_command_entrypoints(self):
        self.assertIn("- name: Shell syntax", self.text)
        self.assertIn("bash -n", self.text)
        for path in COMMAND_ENTRYPOINTS:
            with self.subTest(path=path):
                self.assertGreaterEqual(
                    self.text.count(path),
                    3,
                    f"{path} must be trigger-covered and syntax-checked",
                )

    def test_command_entrypoints_keep_bash_and_strict_mode(self):
        for path in COMMAND_ENTRYPOINTS:
            with self.subTest(path=path):
                lines = (ROOT / path).read_text(encoding="utf-8").splitlines()
                self.assertGreaterEqual(len(lines), 2)
                self.assertEqual(lines[0], "#!/bin/bash")
                self.assertEqual(
                    lines[1],
                    "set -euo pipefail",
                    f"{path} must fail closed on command, unset-variable, and pipeline errors",
                )

    def test_compiles_all_python_quality_tools(self):
        tools = [
            "tools/analyze-watch-sensor-traces.py",
            "tools/analyze-watch-sensor-trials.py",
            "tools/create-physical-observation-template.py",
            "tools/fetch-frozen-physical-handoff.py",
            "tools/validate-physical-observations.py",
            "tools/validate-watch-e2e-evidence.py",
            "tools/verify-watch-apk-identity.py",
        ]
        self.assertIn("python3 -m py_compile", self.text)
        for path in tools:
            with self.subTest(path=path):
                self.assertGreaterEqual(self.text.count(path), 3)

    def test_runs_complete_hosted_quality_regression_set(self):
        modules = [
            "tests.test_adb_device_binding",
            "tests.test_frozen_acceptance_launcher",
            "tests.test_frozen_physical_handoff_fetcher",
            "tests.test_physical_observation_template",
            "tests.test_physical_observation_validator",
            "tests.test_quality_tooling_workflow",
            "tests.test_watch_apk_identity",
            "tests.test_watch_e2e_evidence_validator",
            "tests.test_watch_sensor_trace_analyzer",
            "tests.test_watch_sensor_trial_analyzer",
        ]
        self.assertIn("python3 -m unittest", self.text)
        for module in modules:
            with self.subTest(module=module):
                self.assertIn(module, self.text)

    def test_job_is_read_only_and_bounded(self):
        self.assertIn("permissions:\n  contents: read", self.text)
        self.assertRegex(self.text, r"timeout-minutes:\s*[1-9][0-9]*")
        self.assertIn("cancel-in-progress: true", self.text)

    def test_job_stays_github_hosted_and_secret_free(self):
        self.assertIn("runs-on: ubuntu-latest", self.text)
        self.assertNotIn("self-hosted", self.text)
        self.assertNotRegex(self.text, r"\$\{\{\s*secrets\.")
        self.assertNotRegex(self.text, r"(?m)^\s*environment\s*:")


if __name__ == "__main__":
    unittest.main()
