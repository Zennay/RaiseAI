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
