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

    def test_uses_only_immutable_external_actions(self):
        refs = re.findall(
            r"^\s*(?:-\s*)?uses:\s*([^@\s]+)@([^\s#]+)",
            self.text,
            flags=re.MULTILINE,
        )
        self.assertTrue(refs, "quality workflow must use at least checkout")
        self.assertTrue(
            any(action == "actions/checkout" for action, _ in refs),
            "quality workflow must retain actions/checkout",
        )
        for action, ref in refs:
            if action.startswith("./"):
                continue
            with self.subTest(action=action, ref=ref):
                self.assertRegex(
                    ref,
                    r"^[0-9a-f]{40}$",
                    f"{action} must use an immutable 40-char commit SHA",
                )
        self.assertIn("persist-credentials: false", self.text)
        self.assertNotIn("pull_request_target:", self.text)

    def test_action_execution_surface_is_checkout_only(self):
        refs = re.findall(
            r"^\s*(?:-\s*)?uses:\s*([^@\s]+)@([^\s#]+)",
            self.text,
            flags=re.MULTILINE,
        )
        self.assertEqual(
            [action for action, _ in refs],
            ["actions/checkout"],
            "quality workflow must not expand beyond the audited checkout action",
        )

        lines = self.text.splitlines()
        checkout_index = next(
            index
            for index, line in enumerate(lines)
            if "uses: actions/checkout@" in line
        )
        step_starts = [
            index
            for index, line in enumerate(lines)
            if line.startswith("      - name:")
        ]
        step_start = max(index for index in step_starts if index < checkout_index)
        following_steps = [index for index in step_starts if index > step_start]
        step_end = min(following_steps) if following_steps else len(lines)
        checkout_step = lines[step_start:step_end]
        self.assertIn(
            "          persist-credentials: false",
            checkout_step,
            "checkout must not leave GitHub credentials in the worktree",
        )

    def test_verifies_exact_requested_revision(self):
        expression = (
            "${{ github.event_name == 'pull_request' && "
            "github.event.pull_request.head.sha || github.sha }}"
        )
        lines = self.text.splitlines()

        def step_named(name):
            start = lines.index(f"      - name: {name}")
            following = [
                index
                for index, line in enumerate(lines)
                if index > start and line.startswith("      - name:")
            ]
            end = min(following) if following else len(lines)
            return lines[start:end]

        checkout = step_named("Checkout exact tested revision")
        self.assertIn(
            f"          ref: {expression}",
            checkout,
            "checkout must be bound directly to the requested PR head or push SHA",
        )
        self.assertIn("          persist-credentials: false", checkout)

        verifier = step_named("Verify exact tested revision")
        self.assertIn(
            f"          EXPECTED_SHA: {expression}",
            verifier,
            "revision verifier must compare against the same requested SHA",
        )
        self.assertIn(
            '          test "$(git rev-parse HEAD)" = "$EXPECTED_SHA"',
            verifier,
        )

    def _trigger_paths(self, event):
        lines = self.text.splitlines()
        event_line = f"  {event}:"
        self.assertIn(event_line, lines, f"{event} trigger must exist")
        event_start = lines.index(event_line) + 1

        body = []
        for line in lines[event_start:]:
            if line and not line.startswith("    "):
                break
            body.append(line)

        self.assertIn("    paths:", body, f"{event} trigger must define paths")
        paths_start = body.index("    paths:") + 1
        paths = []
        for line in body[paths_start:]:
            if not line.startswith("      - "):
                break
            match = re.fullmatch(r'      - "([^"]+)"', line)
            self.assertIsNotNone(match, f"unexpected {event} path entry: {line}")
            paths.append(match.group(1))

        self.assertTrue(paths, f"{event} trigger must include at least one path")
        return paths

    def test_push_and_pull_request_filters_cover_quality_surface(self):
        expected_paths = [
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
        for event in ("push", "pull_request"):
            with self.subTest(event=event):
                actual_paths = self._trigger_paths(event)
                self.assertEqual(
                    actual_paths,
                    expected_paths,
                    f"{event} quality paths must be complete, ordered and duplicate-free",
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

    def test_all_run_steps_use_bash_strict_mode(self):
        lines = self.text.splitlines()
        run_indices = [
            index
            for index, line in enumerate(lines)
            if re.match(r"^        run:", line)
        ]
        self.assertTrue(run_indices, "quality workflow must contain run steps")
        self.assertNotIn("continue-on-error: true", self.text)

        step_starts = [
            index
            for index, line in enumerate(lines)
            if line.startswith("      - name:")
        ]
        for run_index in run_indices:
            with self.subTest(run_line=run_index + 1):
                step_start = max(
                    index for index in step_starts if index < run_index
                )
                following_steps = [
                    index for index in step_starts if index > step_start
                ]
                step_end = min(following_steps) if following_steps else len(lines)
                step = lines[step_start:step_end]

                self.assertEqual(
                    lines[run_index],
                    "        run: |",
                    "run steps must use block form so strict mode can be first",
                )
                self.assertIn(
                    "        shell: bash",
                    step,
                    "every run step must explicitly use Bash",
                )
                self.assertLess(run_index + 1, len(lines))
                self.assertEqual(
                    lines[run_index + 1],
                    "          set -euo pipefail",
                    "every run step must fail closed before executing commands",
                )

    def test_permissions_are_exactly_read_only(self):
        permissions = re.search(
            r"(?ms)^permissions:\n((?:  [^\n]+\n)+)",
            self.text,
        )
        self.assertIsNotNone(
            permissions,
            "quality workflow must declare an explicit top-level permissions block",
        )
        self.assertEqual(
            permissions.group(1).splitlines(),
            ["  contents: read"],
            "quality workflow must grant only contents: read",
        )
        self.assertNotRegex(
            self.text,
            r"(?m)^    permissions:",
            "jobs must not override the workflow-level read-only permissions",
        )

    def test_job_is_bounded(self):
        self.assertRegex(self.text, r"timeout-minutes:\s*[1-9][0-9]*")
        self.assertIn("cancel-in-progress: true", self.text)

    def test_quality_execution_is_unconditional(self):
        self.assertNotRegex(
            self.text,
            r"(?m)^\s+if:\s*",
            "dedicated quality jobs and steps must not be conditionally skipped",
        )

    def test_job_timeout_stays_small_and_unique(self):
        timeouts = [
            int(value)
            for value in re.findall(
                r"(?m)^    timeout-minutes:\s*([0-9]+)\s*$",
                self.text,
            )
        ]
        self.assertEqual(
            len(timeouts),
            1,
            "quality workflow must declare exactly one job timeout",
        )
        self.assertGreater(timeouts[0], 0)
        self.assertLessEqual(
            timeouts[0],
            10,
            "hosted quality lane must keep a short fail-closed time budget",
        )

    def test_concurrency_is_namespaced_per_pull_request_or_ref(self):
        self.assertIn(
            "group: raise-quality-tooling-${{ github.event.pull_request.number || github.ref }}",
            self.text,
        )
        self.assertIn("cancel-in-progress: true", self.text)

    def test_hosted_runtime_is_reproducible(self):
        self.assertIn("runs-on: ubuntu-24.04", self.text)
        self.assertNotIn("ubuntu-latest", self.text)
        self.assertIn("LANG: C.UTF-8", self.text)
        self.assertIn('PYTHONHASHSEED: "1"', self.text)
        self.assertIn('PYTHONDONTWRITEBYTECODE: "1"', self.text)
        self.assertIn("TZ: UTC", self.text)
        self.assertIn("- name: Verify Python runtime", self.text)
        self.assertIn('platform.python_implementation() == "CPython"', self.text)
        self.assertIn("sys.version_info[:2] == (3, 12)", self.text)

    def test_job_stays_github_hosted_and_secret_free(self):
        self.assertRegex(self.text, r"runs-on:\s*ubuntu-[0-9]+\.[0-9]+")
        self.assertNotIn("self-hosted", self.text)
        self.assertNotRegex(self.text, r"\$\{\{\s*secrets\.")
        self.assertNotRegex(self.text, r"(?m)^\s*environment\s*:")


if __name__ == "__main__":
    unittest.main()
