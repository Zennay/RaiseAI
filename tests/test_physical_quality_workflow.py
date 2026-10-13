import re
import stat
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "physical-quality-evidence-test.yml"
CHECKOUT_SHA = "3d3c42e5aac5ba805825da76410c181273ba90b1"  # v7.0.1, node24

EXPECTED_PATHS = [
    "physical-validation.command",
    "PHYSICAL-ACCEPTANCE.md",
    "tools/validate-physical-observations.py",
    "tools/create-physical-observation-template.py",
    "tests/test_physical_observation_validator.py",
    "tests/test_physical_observation_template.py",
    "tests/test_quality_workflow_action_pinning.py",
    "tests/test_physical_quality_workflow.py",
    ".github/workflows/watch-app-test.yml",
    ".github/workflows/physical-quality-evidence-test.yml",
]

EXPECTED_ENV = [
    "      LANG: C.UTF-8",
    "      LC_ALL: C.UTF-8",
    '      PYTHONHASHSEED: "1"',
    '      PYTHONNOUSERSITE: "1"',
    '      PYTHONDONTWRITEBYTECODE: "1"',
    "      PYTHONPYCACHEPREFIX: /tmp/raise-physical-quality-pyc",
    "      TZ: UTC",
]


def read_workflow_text(path: Path) -> str:
    mode = path.lstat().st_mode
    if stat.S_ISLNK(mode):
        raise ValueError(f"{path.name}: workflow input must not be a symbolic link")
    if not stat.S_ISREG(mode):
        raise ValueError(f"{path.name}: workflow input must be a regular file")
    try:
        return path.read_bytes().decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise ValueError(f"{path.name}: workflow input must be valid UTF-8") from exc


class PhysicalQualityWorkflowContractTests(unittest.TestCase):
    def setUp(self):
        self.text = read_workflow_text(WORKFLOW)
        self.lines = self.text.splitlines()

    def test_workflow_reader_rejects_symlink_nonregular_and_invalid_utf8(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
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

    def _event_paths(self, event):
        event_line = f"  {event}:"
        start = self.lines.index(event_line) + 1
        block = []
        for line in self.lines[start:]:
            if line and not line.startswith("    "):
                break
            block.append(line)
        paths_start = block.index("    paths:") + 1
        paths = []
        for line in block[paths_start:]:
            match = re.fullmatch(r'      - "([^"]+)"', line)
            if not match:
                break
            paths.append(match.group(1))
        return paths

    def test_trigger_paths_are_exact_and_symmetric(self):
        self.assertEqual(self._event_paths("push"), EXPECTED_PATHS)
        self.assertEqual(self._event_paths("pull_request"), EXPECTED_PATHS)

    def test_hosted_runtime_and_python_environment_are_pinned(self):
        self.assertEqual(self.text.count("    runs-on: ubuntu-24.04"), 1)
        self.assertNotIn("ubuntu-latest", self.text)
        self.assertNotIn("self-hosted", self.text)
        for line in EXPECTED_ENV:
            with self.subTest(line=line):
                self.assertEqual(self.text.count(line), 1)
        runtime = (
            '          python3 -c \'import platform, sys; '
            'assert platform.python_implementation() == "CPython"; '
            'assert sys.version_info[:2] == (3, 12), sys.version\''
        )
        self.assertEqual(self.text.count(runtime), 1)

    def test_external_action_surface_is_exact_and_credential_free(self):
        refs = re.findall(
            r"^\s*(?:-\s*)?uses:\s*([^@\s]+)@([^\s#]+)",
            self.text,
            flags=re.MULTILINE,
        )
        self.assertEqual(refs, [("actions/checkout", CHECKOUT_SHA)])
        self.assertRegex(refs[0][1], r"^[0-9a-f]{40}$")
        self.assertEqual(self.text.count("          persist-credentials: false"), 1)

    def test_permissions_and_exact_head_binding_are_fail_closed(self):
        self.assertRegex(
            self.text,
            r"(?ms)^permissions:\n  contents: read\n\nconcurrency:",
        )
        self.assertNotRegex(self.text, r"(?m)^    permissions:")
        expression = (
            "${{ github.event_name == 'pull_request' && "
            "github.event.pull_request.head.sha || github.sha }}"
        )
        self.assertEqual(self.text.count(f"          ref: {expression}"), 1)
        self.assertIn(
            f'          expected="{expression}"',
            self.text,
        )
        self.assertIn('          test "$revision" = "$expected"', self.text)

    def test_all_run_steps_use_explicit_strict_bash(self):
        step_starts = [
            index
            for index, line in enumerate(self.lines)
            if line.startswith("      - name:")
        ]
        run_indices = [
            index
            for index, line in enumerate(self.lines)
            if line == "        run: |"
        ]
        self.assertTrue(run_indices)
        self.assertNotIn("continue-on-error: true", self.text)
        for run_index in run_indices:
            with self.subTest(line=run_index + 1):
                step_start = max(i for i in step_starts if i < run_index)
                following = [i for i in step_starts if i > step_start]
                step_end = min(following) if following else len(self.lines)
                step = self.lines[step_start:step_end]
                self.assertIn("        shell: bash", step)
                self.assertEqual(self.lines[run_index + 1], "          set -euo pipefail")

    def test_regression_set_includes_workflow_contract(self):
        commands = [
            "python3 -m unittest discover -s tests -p 'test_physical_observation_validator.py'",
            "python3 -m unittest discover -s tests -p 'test_physical_observation_template.py'",
            "python3 -m unittest discover -s tests -p 'test_quality_workflow_action_pinning.py'",
            "python3 -m unittest discover -s tests -p 'test_physical_quality_workflow.py'",
        ]
        for command in commands:
            with self.subTest(command=command):
                self.assertEqual(self.text.count(command), 1)

    def test_clean_worktree_and_secret_free_execution_are_required(self):
        for command in (
            "          git diff --exit-code -- .",
            "          git diff --cached --exit-code -- .",
            '          test -z "$(git ls-files --others --exclude-standard)"',
        ):
            with self.subTest(command=command):
                self.assertEqual(self.text.count(command), 1)
        self.assertNotIn("pull_request_target:", self.text)
        self.assertNotRegex(self.text, r"\$\{\{\s*secrets\.")


if __name__ == "__main__":
    unittest.main()
