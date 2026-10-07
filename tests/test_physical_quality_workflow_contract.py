import pathlib
import re
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "physical-quality-evidence-test.yml"


class PhysicalQualityWorkflowContractTests(unittest.TestCase):
    def setUp(self):
        self.text = WORKFLOW.read_text(encoding="utf-8")
        self.lines = self.text.splitlines()

    def test_runner_and_python_runtime_are_pinned(self):
        self.assertIn("    runs-on: ubuntu-24.04", self.text)
        self.assertNotIn("ubuntu-latest", self.text)
        self.assertNotIn("self-hosted", self.text)
        self.assertIn("- name: Verify Python runtime", self.text)
        self.assertIn('platform.python_implementation() == "CPython"', self.text)
        self.assertIn("sys.version_info[:2] == (3, 12)", self.text)

    def test_reproducible_environment_is_job_scoped(self):
        expected = {
            "LANG": "      LANG: C.UTF-8",
            "LC_ALL": "      LC_ALL: C.UTF-8",
            "PYTHONHASHSEED": '      PYTHONHASHSEED: "1"',
            "PYTHONNOUSERSITE": '      PYTHONNOUSERSITE: "1"',
            "PYTHONDONTWRITEBYTECODE": '      PYTHONDONTWRITEBYTECODE: "1"',
            "PYTHONPYCACHEPREFIX": "      PYTHONPYCACHEPREFIX: /tmp/raise-physical-quality-pyc",
            "TZ": "      TZ: UTC",
        }
        for key, line in expected.items():
            with self.subTest(key=key):
                matches = [current for current in self.lines if re.match(rf"^\\s+{re.escape(key)}:", current)]
                self.assertEqual(matches, [line])

    def test_checkout_is_exact_head_and_credential_free(self):
        expression = ("${{ github.event_name == 'pull_request' && "
                      "github.event.pull_request.head.sha || github.sha }}")
        self.assertIn(
            "uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1 (node24)",
            self.text,
        )
        self.assertIn(f"          ref: {expression}", self.text)
        self.assertIn("          persist-credentials: false", self.text)

    def test_every_run_step_uses_explicit_strict_bash(self):
        run_indices = [i for i, line in enumerate(self.lines) if line == "        run: |"]
        self.assertTrue(run_indices)
        for run_index in run_indices:
            step_start = max(i for i, line in enumerate(self.lines) if i < run_index and line.startswith("      - "))
            step = self.lines[step_start:run_index + 3]
            with self.subTest(step=self.lines[step_start]):
                self.assertIn("        shell: bash", step)
                self.assertEqual(self.lines[run_index + 1], "          set -euo pipefail")
        self.assertNotIn("continue-on-error: true", self.text)

    def test_contract_triggers_and_runs_itself(self):
        self.assertEqual(
            self.text.count('      - "tests/test_physical_quality_workflow_contract.py"'),
            2,
        )
        self.assertIn("python3 -m unittest tests.test_physical_quality_workflow_contract", self.text)

    def test_permissions_and_timeout_stay_narrow(self):
        permissions = re.search(r"(?ms)^permissions:\\n((?:  [^\\n]+\\n)+)", self.text)
        self.assertIsNotNone(permissions)
        self.assertEqual(permissions.group(1).splitlines(), ["  contents: read"])
        self.assertNotRegex(self.text, r"\\$\\{\\{\\s*secrets\\.")
        self.assertIn("    timeout-minutes: 5", self.text)


if __name__ == "__main__":
    unittest.main()
