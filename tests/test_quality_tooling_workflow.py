import importlib.util
import pathlib
import re
import stat
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "quality-tooling-test.yml"
RUNNER = ROOT / "tools" / "run_quality_tooling_contracts.py"
RUNNER_SPEC = importlib.util.spec_from_file_location(
    "raise_quality_tooling_runner_contract",
    RUNNER,
)
if RUNNER_SPEC is None or RUNNER_SPEC.loader is None:
    raise RuntimeError("could not load quality tooling contract runner")
RUNNER_MODULE = importlib.util.module_from_spec(RUNNER_SPEC)
RUNNER_SPEC.loader.exec_module(RUNNER_MODULE)
QUALITY_MODULES = RUNNER_MODULE.QUALITY_MODULES
STRICT_COMMAND_ENTRYPOINTS = [
    "pull-diagnostics.command",
    "pull-watch-data.command",
    "install-watch-apk.command",
    "provision-watch-gateway.command",
    "physical-validation.command",
    "start-frozen-acceptance.command",
    "start-physical-handoff.command",
]
POWERSHELL_SYNTAX_ENTRYPOINTS = ["install-watch-windows.ps1"]
def read_workflow_text(path: pathlib.Path) -> str:
    mode = path.lstat().st_mode
    if stat.S_ISLNK(mode):
        raise ValueError(f"{path.name}: workflow input must not be a symbolic link")
    if not stat.S_ISREG(mode):
        raise ValueError(f"{path.name}: workflow input must be a regular file")
    try:
        return path.read_bytes().decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise ValueError(f"{path.name}: workflow input must be valid UTF-8") from exc


SHELL_SYNTAX_ENTRYPOINTS = [
    "install-gesture-watch.command",
    "upgrade-watch.command",
    "watch-preflight.command",
    "login-from-mac.command",
    "open-in-android-studio.command",
    "setup-and-install-watch.command",
    "install-mac-adb-autoconnect.command",
    *STRICT_COMMAND_ENTRYPOINTS,
]


class QualityToolingWorkflowContractTests(unittest.TestCase):
    def setUp(self):
        self.text = read_workflow_text(WORKFLOW)

    def test_workflow_reader_rejects_symlink_nonregular_and_invalid_utf8(self):
        with tempfile.TemporaryDirectory() as temp:
            root = pathlib.Path(temp)
            regular = root / "regular.yml"
            regular.write_text("on: [push]\n", encoding="utf-8")
            self.assertEqual(read_workflow_text(regular), "on: [push]\n")

            linked = root / "linked.yml"
            linked.symlink_to(regular)
            with self.assertRaisesRegex(ValueError, "must not be a symbolic link"):
                read_workflow_text(linked)

            directory = root / "directory.yml"
            directory.mkdir()
            with self.assertRaisesRegex(ValueError, "must be a regular file"):
                read_workflow_text(directory)

            invalid = root / "invalid.yml"
            invalid.write_bytes(b"on: [push]\n\xff")
            with self.assertRaisesRegex(ValueError, "must be valid UTF-8"):
                read_workflow_text(invalid)

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

    def test_checkout_action_uses_audited_node24_release(self):
        self.assertIn(
            "uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 "
            "# v7.0.1 (node24)",
            self.text,
        )
        self.assertNotIn(
            "actions/checkout@11d5960a326750d5838078e36cf38b85af677262",
            self.text,
            "deprecated checkout v4/Node 20 pin must not return",
        )

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
            "*.command",
            "*.py",
            "*.ps1",
            "tools/*.py",
            "tests/__init__.py",
            "tests/test_adb_device_binding.py",
            "tests/test_all_workflow_action_pins.py",
            "tests/test_frozen_acceptance_launcher.py",
            "tests/test_frozen_physical_handoff_fetcher.py",
            "tests/test_physical_observation_template.py",
            "tests/test_physical_observation_validator.py",
            "tests/test_physical_validation_cli.py",
            "tests/test_quality_tooling_workflow.py",
            "tests/test_quality_tooling_runner.py",
            "tests/test_quality_workflow_action_pinning.py",
            "tests/test_source_text_review_integrity.py",
            "tests/test_watch_data_analyzer.py",
            "tests/test_watch_apk_identity.py",
            "tests/test_watch_e2e_evidence_validator.py",
            "tests/test_watch_sensor_trace_analyzer.py",
            "tests/test_watch_sensor_trial_analyzer.py",
            ".github/actions/**/action.yml",
            ".github/actions/**/action.yaml",
            ".github/workflows/*.yml",
            ".github/workflows/*.yaml",
        ]
        for event in ("push", "pull_request"):
            with self.subTest(event=event):
                actual_paths = self._trigger_paths(event)
                self.assertEqual(
                    actual_paths,
                    expected_paths,
                    f"{event} quality paths must be complete, ordered and duplicate-free",
                )

    def test_shell_syntax_surface_matches_every_root_command_entrypoint(self):
        discovered = sorted(path.name for path in ROOT.glob("*.command"))
        self.assertEqual(
            sorted(SHELL_SYNTAX_ENTRYPOINTS),
            discovered,
            "every root .command entrypoint must be covered by hosted syntax validation",
        )

    def test_checks_shell_syntax_for_all_command_entrypoints(self):
        self.assertIn("- name: Shell syntax", self.text)
        self.assertIn("bash -n -- *.command", self.text)
        self.assertEqual(self._trigger_paths("push")[0], "*.command")
        self.assertEqual(self._trigger_paths("pull_request")[0], "*.command")
        self.assertIn(
            "bash -n -- *.command",
            self.text,
            "hosted shell syntax validation must cover the entire reviewed root command set",
        )

    def test_strict_command_entrypoints_keep_bash_and_strict_mode(self):
        for path in STRICT_COMMAND_ENTRYPOINTS:
            with self.subTest(path=path):
                lines = (ROOT / path).read_text(encoding="utf-8").splitlines()
                self.assertGreaterEqual(len(lines), 2)
                self.assertEqual(lines[0], "#!/bin/bash")
                self.assertEqual(
                    lines[1],
                    "set -euo pipefail",
                    f"{path} must fail closed on command, unset-variable, and pipeline errors",
                )

    def test_root_python_entrypoints_trigger_and_compile_automatically(self):
        for event in ("push", "pull_request"):
            with self.subTest(event=event):
                self.assertEqual(self._trigger_paths(event)[:2], ["*.command", "*.py"])
        self.assertIn("python3 -I -m py_compile *.py ", self.text)
        discovered = sorted(path.name for path in ROOT.glob("*.py"))
        self.assertTrue(discovered, "repository must retain at least one root Python entrypoint")
        for path in discovered:
            with self.subTest(path=path):
                self.assertTrue(path.endswith(".py"))

    def test_root_powershell_entrypoints_trigger_and_parse_automatically(self):
        discovered = sorted(path.name for path in ROOT.glob("*.ps1"))
        self.assertEqual(
            POWERSHELL_SYNTAX_ENTRYPOINTS,
            discovered,
            "every root .ps1 entrypoint must be covered by hosted syntax validation",
        )
        for event in ("push", "pull_request"):
            with self.subTest(event=event):
                self.assertEqual(
                    self._trigger_paths(event)[:3],
                    ["*.command", "*.py", "*.ps1"],
                )
        self.assertIn("- name: PowerShell syntax", self.text)
        self.assertIn("command -v pwsh >/dev/null", self.text)
        self.assertIn(
            "System.Management.Automation.Language.Parser]::ParseFile",
            self.text,
        )
        self.assertIn(
            'Get-ChildItem -LiteralPath . -File -Filter "*.ps1" | Sort-Object Name',
            self.text,
        )
        self.assertIn("if ($files.Count -eq 0)", self.text)
        self.assertIn(
            'Get-ChildItem -LiteralPath . -File -Filter "*.ps1" | Sort-Object Name',
            self.text,
            "hosted PowerShell syntax validation must discover every reviewed root entrypoint",
        )

    def test_compiles_all_python_quality_tools(self):
        self.assertIn("tools/*.py", self._trigger_paths("push"))
        self.assertIn("tools/*.py", self._trigger_paths("pull_request"))
        self.assertIn("python3 -I -m py_compile *.py tools/*.py", self.text)
        self.assertNotIn(
            "python3 -m py_compile",
            self.text,
            "hosted Python syntax validation must not allow ambient import-path customization",
        )
        discovered = sorted(path.name for path in (ROOT / "tools").glob("*.py"))
        self.assertTrue(discovered, "tools/ must retain Python quality tooling")

    def test_runs_complete_hosted_quality_regression_set_in_isolated_mode(self):
        modules = (
            "tests.test_adb_device_binding",
            "tests.test_all_workflow_action_pins",
            "tests.test_frozen_acceptance_launcher",
            "tests.test_frozen_physical_handoff_fetcher",
            "tests.test_physical_observation_template",
            "tests.test_physical_observation_validator",
            "tests.test_physical_validation_cli",
            "tests.test_quality_tooling_runner",
            "tests.test_quality_tooling_workflow",
            "tests.test_quality_workflow_action_pinning",
            "tests.test_source_text_review_integrity",
            "tests.test_watch_data_analyzer",
            "tests.test_watch_apk_identity",
            "tests.test_watch_e2e_evidence_validator",
            "tests.test_wear_extension_asset_contract",
            "tests.test_watch_sensor_trace_analyzer",
            "tests.test_watch_sensor_trial_analyzer",
        )
        self.assertEqual(QUALITY_MODULES, modules)
        self.assertIn(
            "python3 -I tools/run_quality_tooling_contracts.py",
            self.text,
        )
        self.assertNotIn(
            "python3 -m unittest",
            self.text,
            "hosted quality regressions must not re-enable environment-controlled imports",
        )

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
        self.assertIn("LC_ALL: C.UTF-8", self.text)
        self.assertIn('PYTHONHASHSEED: "1"', self.text)
        self.assertIn('PYTHONNOUSERSITE: "1"', self.text)
        self.assertIn('PYTHONDONTWRITEBYTECODE: "1"', self.text)
        self.assertIn("PYTHONPYCACHEPREFIX: /tmp/raise-quality-pyc", self.text)
        self.assertIn("TZ: UTC", self.text)
        self.assertIn("- name: Verify Python runtime", self.text)
        self.assertIn(
            "python3 -I -c 'import platform, sys;",
            self.text,
        )
        self.assertNotIn(
            "python3 -c 'import platform, sys;",
            self.text,
            "runtime verification must not allow ambient import-path customization",
        )
        self.assertIn('platform.python_implementation() == "CPython"', self.text)
        self.assertIn("sys.version_info[:2] == (3, 12)", self.text)

    def test_job_stays_github_hosted_and_secret_free(self):
        self.assertRegex(self.text, r"runs-on:\s*ubuntu-[0-9]+\.[0-9]+")
        self.assertNotIn("self-hosted", self.text)
        self.assertNotRegex(self.text, r"\$\{\{\s*secrets\.")
        self.assertNotRegex(self.text, r"(?m)^\s*environment\s*:")


    def test_critical_yaml_mapping_keys_are_unique(self):
        for key in ("on", "permissions", "concurrency", "jobs"):
            with self.subTest(scope="top-level", key=key):
                matches = re.findall(
                    rf"(?m)^{re.escape(key)}:\s*$",
                    self.text,
                )
                self.assertEqual(
                    len(matches),
                    1,
                    f"top-level {key!r} mapping must appear exactly once",
                )

        jobs_block = self.text.split("\njobs:\n", 1)[1]
        job_names = re.findall(r"(?m)^  ([A-Za-z0-9_-]+):\s*$", jobs_block)
        self.assertEqual(
            job_names,
            ["python-quality"],
            "hosted quality workflow must remain a single audited job",
        )

        for key in ("runs-on", "timeout-minutes", "env", "steps"):
            with self.subTest(scope="python-quality", key=key):
                matches = re.findall(
                    rf"(?m)^    {re.escape(key)}:[^\n]*$",
                    jobs_block,
                )
                self.assertEqual(
                    len(matches),
                    1,
                    f"python-quality {key!r} mapping must appear exactly once",
                )

        for key in ("container", "services", "strategy", "permissions"):
            with self.subTest(scope="python-quality", forbidden_key=key):
                self.assertNotRegex(
                    jobs_block,
                    rf"(?m)^    {re.escape(key)}:",
                    f"python-quality must not add job-level {key!r}",
                )

    def test_trigger_surface_stays_push_and_pull_request_only(self):
        lines = self.text.splitlines()
        on_start = lines.index("on:") + 1
        permissions_start = lines.index("permissions:")
        trigger_lines = lines[on_start:permissions_start]
        events = []
        for line in trigger_lines:
            match = re.fullmatch(r"  ([A-Za-z0-9_-]+):", line)
            if match:
                events.append(match.group(1))

        self.assertEqual(
            events,
            ["push", "pull_request"],
            "dedicated quality lane must not gain extra trigger surfaces",
        )

    def test_reproducible_environment_keys_cannot_be_shadowed(self):
        expected_lines = {
            "LANG": "      LANG: C.UTF-8",
            "LC_ALL": "      LC_ALL: C.UTF-8",
            "PYTHONHASHSEED": '      PYTHONHASHSEED: "1"',
            "PYTHONNOUSERSITE": '      PYTHONNOUSERSITE: "1"',
            "PYTHONDONTWRITEBYTECODE": '      PYTHONDONTWRITEBYTECODE: "1"',
            "PYTHONPYCACHEPREFIX": "      PYTHONPYCACHEPREFIX: /tmp/raise-quality-pyc",
            "TZ": "      TZ: UTC",
        }
        for key, expected_line in expected_lines.items():
            with self.subTest(key=key):
                matches = [
                    line
                    for line in self.text.splitlines()
                    if re.match(rf"^\s+{re.escape(key)}:", line)
                ]
                self.assertEqual(
                    matches,
                    [expected_line],
                    f"{key} must be declared exactly once at job scope",
                )


    def test_exact_head_checkout_keys_cannot_be_shadowed(self):
        expression = (
            "${{ github.event_name == 'pull_request' && "
            "github.event.pull_request.head.sha || github.sha }}"
        )
        expected = {
            "ref": f"          ref: {expression}",
            "persist-credentials": "          persist-credentials: false",
            "EXPECTED_SHA": f"          EXPECTED_SHA: {expression}",
        }
        for key, expected_line in expected.items():
            with self.subTest(key=key):
                matches = [
                    line
                    for line in self.text.splitlines()
                    if re.match(rf"^\s+{re.escape(key)}:", line)
                ]
                self.assertEqual(
                    matches,
                    [expected_line],
                    f"{key} must be declared exactly once with the audited value",
                )

    def test_concurrency_contract_cannot_be_shadowed(self):
        lines = self.text.splitlines()
        start = lines.index("concurrency:") + 1
        end = lines.index("jobs:")
        block = lines[start:end]
        keys = []
        for line in block:
            match = re.fullmatch(r"  ([A-Za-z0-9_-]+):.*", line)
            if match:
                keys.append(match.group(1))

        self.assertEqual(
            keys,
            ["group", "cancel-in-progress"],
            "concurrency mapping must contain only the audited keys once each",
        )
        self.assertEqual(
            [
                line
                for line in block
                if line.startswith("  cancel-in-progress:")
            ],
            ["  cancel-in-progress: true"],
            "stale quality runs must always be cancelled",
        )


    def test_trigger_ref_scope_is_exact(self):
        lines = self.text.splitlines()

        def event_block(event):
            event_line = f"  {event}:"
            self.assertIn(event_line, lines, f"{event} trigger must exist")
            start = lines.index(event_line) + 1
            block = []
            for line in lines[start:]:
                if line and not line.startswith("    "):
                    break
                block.append(line)
            return block

        push = event_block("push")
        push_keys = []
        for line in push:
            match = re.fullmatch(r"    ([A-Za-z0-9_-]+):", line)
            if match:
                push_keys.append(match.group(1))
        self.assertEqual(
            push_keys,
            ["branches", "paths"],
            "push must remain scoped only by the audited main branch and quality paths",
        )

        branches_start = push.index("    branches:") + 1
        branches = []
        for line in push[branches_start:]:
            match = re.fullmatch(r"      - ([A-Za-z0-9_.-]+)", line)
            if match:
                branches.append(match.group(1))
                continue
            break
        self.assertEqual(
            branches,
            ["main"],
            "hosted quality push validation must run only for main",
        )

        pull_request = event_block("pull_request")
        pull_request_keys = []
        for line in pull_request:
            match = re.fullmatch(r"    ([A-Za-z0-9_-]+):", line)
            if match:
                pull_request_keys.append(match.group(1))
        self.assertEqual(
            pull_request_keys,
            ["paths"],
            "pull_request must not gain branch, type, or other filters that can skip quality validation",
        )


    def test_python_quality_job_mapping_surface_is_exact(self):
        jobs_block = self.text.split("\njobs:\n", 1)[1]
        job_lines = jobs_block.splitlines()
        job_start = job_lines.index("  python-quality:") + 1
        job_body = job_lines[job_start:]

        keys = []
        for line in job_body:
            match = re.fullmatch(r"    ([A-Za-z0-9_-]+):.*", line)
            if match:
                keys.append(match.group(1))

        self.assertEqual(
            keys,
            ["runs-on", "timeout-minutes", "env", "steps"],
            "python-quality must not gain unreviewed job-level execution controls",
        )


    def test_quality_step_mapping_surfaces_are_exact(self):
        lines = self.text.splitlines()
        step_starts = [
            index
            for index, line in enumerate(lines)
            if line.startswith("      - name:")
        ]
        self.assertEqual(
            [lines[index].removeprefix("      - name: ") for index in step_starts],
            [
                "Checkout exact tested revision",
                "Verify exact tested revision",
                "Verify Python runtime",
                "Shell syntax",
                "Python syntax",
                "PowerShell syntax",
                "Quality tooling regressions",
                "Verify worktree remains clean",
            ],
            "hosted quality step list must remain explicit and ordered",
        )

        expected_keys = {
            "Checkout exact tested revision": ["name", "uses", "with"],
            "Verify exact tested revision": ["name", "shell", "env", "run"],
            "Verify Python runtime": ["name", "shell", "run"],
            "Shell syntax": ["name", "shell", "run"],
            "Python syntax": ["name", "shell", "run"],
            "PowerShell syntax": ["name", "shell", "run"],
            "Quality tooling regressions": ["name", "shell", "run"],
            "Verify worktree remains clean": ["name", "shell", "run"],
        }
        for position, start in enumerate(step_starts):
            end = step_starts[position + 1] if position + 1 < len(step_starts) else len(lines)
            step = lines[start:end]
            name = lines[start].removeprefix("      - name: ")
            keys = ["name"]
            for line in step[1:]:
                match = re.fullmatch(r"        ([A-Za-z0-9_-]+):.*", line)
                if match:
                    keys.append(match.group(1))
            self.assertEqual(
                keys,
                expected_keys[name],
                f"{name} must not gain unreviewed step-level execution controls",
            )


    def test_workflow_top_level_surface_is_exact(self):
        lines = self.text.splitlines()
        top_level_keys = []
        for line in lines:
            match = re.fullmatch(r"([A-Za-z0-9_-]+):.*", line)
            if match:
                top_level_keys.append(match.group(1))

        self.assertEqual(
            top_level_keys,
            ["name", "on", "permissions", "concurrency", "jobs"],
            "hosted quality workflow must not gain global defaults, env, run-name, or other top-level controls",
        )
        self.assertEqual(
            lines[0],
            "name: Raise quality tooling CI",
            "required-check identity must remain stable",
        )


    def test_workflow_avoids_yaml_indirection(self):
        self.assertNotRegex(
            self.text,
            r"(?m)(?:^|\s)&[A-Za-z0-9_-]+",
            "YAML anchors can hide execution semantics from the text-level quality contract",
        )
        self.assertNotRegex(
            self.text,
            r"(?m)(?:^|\s)\*[A-Za-z0-9_-]+",
            "YAML aliases can reintroduce hidden mappings outside the audited surface",
        )
        self.assertNotRegex(
            self.text,
            r"(?m)^\s*<<:\s*",
            "YAML merge keys are forbidden in the dedicated hosted quality workflow",
        )


    def test_workflow_rejects_quoted_mapping_keys(self):
        quoted_mapping_key = re.compile(
            r'''(?m)^\s*(?:"[^"\n]+"|'[^'\n]+')\s*:'''
        )
        fixtures = (
            '        "continue-on-error": true',
            "        'working-directory': /tmp",
            '      "timeout-minutes": 30',
            "  'pull_request_target':",
        )
        for fixture in fixtures:
            with self.subTest(fixture=fixture):
                self.assertRegex(
                    fixture,
                    quoted_mapping_key,
                    "regression fixture must exercise the quoted-key detector",
                )

        self.assertNotRegex(
            self.text,
            quoted_mapping_key,
            "quoted YAML mapping keys can bypass the hosted quality exact-surface parsers",
        )


    def test_reproducibility_nested_mapping_surfaces_are_exact(self):
        lines = self.text.splitlines()

        job_env_start = lines.index("    env:") + 1
        job_env_keys = []
        for line in lines[job_env_start:]:
            match = re.fullmatch(r"      ([A-Za-z0-9_-]+):.*", line)
            if match:
                job_env_keys.append(match.group(1))
                continue
            break
        self.assertEqual(
            job_env_keys,
            ["LANG", "LC_ALL", "PYTHONHASHSEED", "PYTHONNOUSERSITE", "PYTHONDONTWRITEBYTECODE", "PYTHONPYCACHEPREFIX", "TZ"],
            "python-quality job env must not gain unreviewed variables",
        )

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
        with_start = checkout.index("        with:") + 1
        with_keys = []
        for line in checkout[with_start:]:
            match = re.fullmatch(r"          ([A-Za-z0-9_-]+):.*", line)
            if match:
                with_keys.append(match.group(1))
                continue
            break
        self.assertEqual(
            with_keys,
            ["ref", "persist-credentials"],
            "checkout with: mapping must remain limited to exact-head binding and credential removal",
        )

        verifier = step_named("Verify exact tested revision")
        env_start = verifier.index("        env:") + 1
        verifier_env_keys = []
        for line in verifier[env_start:]:
            match = re.fullmatch(r"          ([A-Za-z0-9_-]+):.*", line)
            if match:
                verifier_env_keys.append(match.group(1))
                continue
            break
        self.assertEqual(
            verifier_env_keys,
            ["EXPECTED_SHA"],
            "revision verifier env must not gain unreviewed variables",
        )


    def test_quality_run_command_bodies_are_exact(self):
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

        expected_commands = {
            "Verify exact tested revision": [
                "set -euo pipefail",
                'test "$(git rev-parse HEAD)" = "$EXPECTED_SHA"',
            ],
            "Verify Python runtime": [
                "set -euo pipefail",
                "python3 -I -c 'import platform, sys; assert platform.python_implementation() == \"CPython\"; assert sys.version_info[:2] == (3, 12), sys.version'",
            ],
            "Shell syntax": [
                "set -euo pipefail",
                "bash -n -- *.command",
            ],
            "Python syntax": [
                "set -euo pipefail",
                "python3 -I -m py_compile *.py tools/*.py",
            ],
            "PowerShell syntax": [
                "set -euo pipefail",
                "command -v pwsh >/dev/null",
                "pwsh -NoLogo -NoProfile -NonInteractive -Command '$files = @(Get-ChildItem -LiteralPath . -File -Filter \"*.ps1\" | Sort-Object Name); if ($files.Count -eq 0) { Write-Error \"No root PowerShell entrypoints found\"; exit 1 }; foreach ($file in $files) { $tokens = $null; $errors = $null; [void][System.Management.Automation.Language.Parser]::ParseFile($file.FullName, [ref]$tokens, [ref]$errors); if ($errors.Count -ne 0) { $errors | ForEach-Object { Write-Error \"$($file.Name): $($_.Message)\" }; exit 1 } }'",
            ],
            "Quality tooling regressions": [
                "set -euo pipefail",
                "python3 -I tools/run_quality_tooling_contracts.py",
            ],
            "Verify worktree remains clean": [
                "set -euo pipefail",
                "git diff --exit-code -- .",
                "git diff --cached --exit-code -- .",
                'test -z "$(git ls-files --others --exclude-standard)"',
            ],
        }

        for name, expected in expected_commands.items():
            with self.subTest(step=name):
                step = step_named(name)
                run_start = step.index("        run: |") + 1
                commands = []
                for line in step[run_start:]:
                    if line.startswith("          "):
                        commands.append(line.removeprefix("          "))
                        continue
                    break
                self.assertEqual(
                    commands,
                    expected,
                    f"{name} run body must remain exactly audited",
                )


if __name__ == "__main__":
    unittest.main()
