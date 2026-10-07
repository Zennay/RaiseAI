import pathlib
import re
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "gradle-properties-contract.yml"
PROPERTIES = ROOT / "gradle.properties"
EXPECTED = {
    "org.gradle.jvmargs": "-Xmx2048m -Dfile.encoding=UTF-8",
    "android.useAndroidX": "true",
    "kotlin.code.style": "official",
}


def parse_properties(text):
    values = {}
    for number, raw_line in enumerate(text.splitlines(), start=1):
        line = raw_line.strip()
        if not line or line.startswith("#") or line.startswith("!"):
            continue
        if "=" not in line:
            raise ValueError(f"line {number}: expected key=value")
        key, value = (part.strip() for part in line.split("=", 1))
        if not key:
            raise ValueError(f"line {number}: empty key")
        if key in values:
            raise ValueError(f"line {number}: duplicate key {key}")
        values[key] = value
    return values


class GradlePropertiesContractTests(unittest.TestCase):
    def setUp(self):
        self.workflow = WORKFLOW.read_text(encoding="utf-8")

    def test_current_gradle_properties_matches_exact_contract(self):
        self.assertFalse(PROPERTIES.is_symlink())
        self.assertTrue(PROPERTIES.is_file())
        raw = PROPERTIES.read_bytes()
        self.assertNotIn(b"\x00", raw)
        text = raw.decode("utf-8")
        self.assertEqual(parse_properties(text), EXPECTED)

    def test_parser_rejects_duplicate_key(self):
        with self.assertRaisesRegex(ValueError, "duplicate key android.useAndroidX"):
            parse_properties(
                "android.useAndroidX=true\n"
                "android.useAndroidX=false\n"
            )

    def test_parser_rejects_non_assignment(self):
        with self.assertRaisesRegex(ValueError, "expected key=value"):
            parse_properties("android.useAndroidX true\n")

    def _trigger_paths(self, event):
        lines = self.workflow.splitlines()
        start = lines.index(f"  {event}:") + 1
        body = []
        for line in lines[start:]:
            if line and not line.startswith("    "):
                break
            body.append(line)
        self.assertIn("    paths:", body)
        index = body.index("    paths:") + 1
        paths = []
        for line in body[index:]:
            match = re.fullmatch(r'      - "([^"]+)"', line)
            if not match:
                break
            paths.append(match.group(1))
        return paths

    def test_workflow_triggers_cover_contract_inputs(self):
        expected = [
            "gradle.properties",
            "tests/test_gradle_properties_contract.py",
            ".github/workflows/gradle-properties-contract.yml",
        ]
        for event in ("push", "pull_request"):
            with self.subTest(event=event):
                self.assertEqual(self._trigger_paths(event), expected)

    def test_workflow_is_hosted_read_only_exact_head_and_bounded(self):
        self.assertIn("runs-on: ubuntu-24.04", self.workflow)
        self.assertNotIn("self-hosted", self.workflow)
        self.assertIn("permissions:\n  contents: read\n", self.workflow)
        self.assertNotRegex(self.workflow, r"\$\{\{\s*secrets\.")
        self.assertIn("timeout-minutes: 5", self.workflow)
        self.assertIn("cancel-in-progress: true", self.workflow)
        expression = (
            "${{ github.event_name == 'pull_request' && "
            "github.event.pull_request.head.sha || github.sha }}"
        )
        self.assertEqual(self.workflow.count(expression), 2)
        self.assertIn("persist-credentials: false", self.workflow)

    def test_workflow_pins_exact_python_runtime(self):
        assertion = (
            'python3 -c \'import platform, sys; '
            'assert platform.python_implementation() == "CPython"; '
            'assert sys.version_info[:2] == (3, 12), sys.version\''
        )
        self.assertEqual(
            self.workflow.count(assertion),
            1,
            "Gradle properties validation must remain pinned to CPython 3.12",
        )

    def test_workflow_uses_only_immutable_checkout_action(self):
        refs = re.findall(
            r"^\s*(?:-\s*)?uses:\s*([^@\s]+)@([^\s#]+)",
            self.workflow,
            flags=re.MULTILINE,
        )
        self.assertEqual([action for action, _ in refs], ["actions/checkout"])
        self.assertRegex(refs[0][1], r"^[0-9a-f]{40}$")

    def test_workflow_locks_exact_gradle_properties_contract(self):
        for token in (
            'path = pathlib.Path("gradle.properties")',
            "path.is_symlink()",
            "path.is_file()",
            'path.read_bytes().decode("utf-8")',
            'if "\\x00" in text:',
            '"org.gradle.jvmargs": "-Xmx2048m -Dfile.encoding=UTF-8"',
            '"android.useAndroidX": "true"',
            '"kotlin.code.style": "official"',
            "if values != expected:",
            "python3 -m unittest tests.test_gradle_properties_contract",
            "git diff --exit-code -- .",
            'test -z "$(git ls-files --others --exclude-standard)"',
        ):
            with self.subTest(token=token):
                self.assertIn(token, self.workflow)

    def test_workflow_top_level_job_and_environment_surfaces_are_exact(self):
        lines = self.workflow.splitlines()

        top_level = []
        for line in lines:
            match = re.fullmatch(r"([A-Za-z0-9_-]+):.*", line)
            if match:
                top_level.append(match.group(1))
        self.assertEqual(
            top_level,
            ["name", "on", "permissions", "concurrency", "jobs"],
            "Gradle properties workflow must not gain unreviewed top-level controls",
        )

        jobs_block = self.workflow.split("\njobs:\n", 1)[1]
        job_keys = []
        for line in jobs_block.splitlines()[1:]:
            match = re.fullmatch(r"    ([A-Za-z0-9_-]+):.*", line)
            if match:
                job_keys.append(match.group(1))
        self.assertEqual(
            job_keys,
            ["runs-on", "timeout-minutes", "env", "steps"],
            "Gradle properties verify job must keep an exact execution surface",
        )

        env_start = lines.index("    env:") + 1
        expected_env_lines = [
            "      LANG: C.UTF-8",
            "      LC_ALL: C.UTF-8",
            '      PYTHONHASHSEED: "1"',
            '      PYTHONNOUSERSITE: "1"',
            '      PYTHONDONTWRITEBYTECODE: "1"',
            "      TZ: UTC",
        ]
        actual_env_lines = lines[env_start : env_start + len(expected_env_lines)]
        self.assertEqual(
            actual_env_lines,
            expected_env_lines,
            "Gradle properties job environment must remain deterministic",
        )
        following = lines[env_start + len(expected_env_lines)]
        self.assertEqual(
            following,
            "    steps:",
            "Gradle properties job environment must not gain extra variables",
        )

    def test_step_mapping_surfaces_are_exact(self):
        lines = self.workflow.splitlines()
        step_starts = [
            index
            for index, line in enumerate(lines)
            if line.startswith("      - name:")
        ]
        expected_names = [
            "Checkout exact tested revision",
            "Verify exact tested revision",
            "Verify Python runtime",
            "Validate Gradle properties contract",
            "Run Gradle properties regression contract",
            "Verify worktree remains clean",
        ]
        names = [
            lines[index].removeprefix("      - name: ")
            for index in step_starts
        ]
        self.assertEqual(
            names,
            expected_names,
            "Gradle properties workflow must not gain unreviewed steps",
        )

        expected_keys = {
            "Checkout exact tested revision": ["name", "uses", "with"],
            "Verify exact tested revision": ["name", "shell", "env", "run"],
            "Verify Python runtime": ["name", "shell", "run"],
            "Validate Gradle properties contract": ["name", "shell", "run"],
            "Run Gradle properties regression contract": ["name", "shell", "run"],
            "Verify worktree remains clean": ["name", "shell", "run"],
        }
        for position, start in enumerate(step_starts):
            end = (
                step_starts[position + 1]
                if position + 1 < len(step_starts)
                else len(lines)
            )
            step = lines[start:end]
            name = names[position]
            keys = ["name"]
            for line in step[1:]:
                match = re.fullmatch(r"        ([A-Za-z0-9_-]+):.*", line)
                if match:
                    keys.append(match.group(1))
            self.assertEqual(
                keys,
                expected_keys[name],
                f"{name} must not gain unreviewed step-level controls",
            )

    def test_all_run_steps_are_explicit_strict_bash(self):
        lines = self.workflow.splitlines()
        run_indices = [index for index, line in enumerate(lines) if line == "        run: |"]
        self.assertTrue(run_indices)
        step_starts = [
            index for index, line in enumerate(lines) if line.startswith("      - name:")
        ]
        for run_index in run_indices:
            with self.subTest(line=run_index + 1):
                step_start = max(index for index in step_starts if index < run_index)
                following = [index for index in step_starts if index > step_start]
                step_end = min(following) if following else len(lines)
                step = lines[step_start:step_end]
                self.assertIn("        shell: bash", step)
                self.assertEqual(lines[run_index + 1], "          set -euo pipefail")
        self.assertNotIn("continue-on-error: true", self.workflow)
        self.assertNotRegex(self.workflow, r"(?m)^\s+if:\s*")


if __name__ == "__main__":
    unittest.main()
