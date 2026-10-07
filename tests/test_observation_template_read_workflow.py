from pathlib import Path
import re
import stat
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "observation-template-read-integrity.yml"
CHECKOUT_SHA = "3d3c42e5aac5ba805825da76410c181273ba90b1"


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


class ObservationTemplateReadWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.text = read_workflow_text(WORKFLOW)

    def test_workflow_reader_rejects_symlink_nonregular_and_invalid_utf8(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            regular = root / "regular.yml"
            regular.write_text("on: [push]\n", encoding="utf-8")
            linked = root / "linked.yml"
            linked.symlink_to(regular)
            with self.assertRaisesRegex(ValueError, "must not be a symbolic link"):
                read_workflow_text(linked)

            directory = root / "directory.yml"
            directory.mkdir()
            with self.assertRaisesRegex(ValueError, "must be a regular file"):
                read_workflow_text(directory)

            invalid = root / "invalid.yml"
            invalid.write_bytes(b"on: [push]\xff")
            with self.assertRaisesRegex(ValueError, "must be valid UTF-8"):
                read_workflow_text(invalid)

    def test_lane_is_hosted_read_only_and_secret_free(self):
        self.assertIn("    runs-on: ubuntu-24.04", self.text)
        self.assertNotIn("self-hosted", self.text)
        self.assertNotIn("ubuntu-latest", self.text)
        self.assertRegex(
            self.text,
            r"(?ms)^permissions:\n  contents: read\n\nconcurrency:",
        )
        self.assertNotRegex(self.text, r"(?m)^    permissions:")
        self.assertNotRegex(self.text, r"\$\{\{\s*secrets\.")
        self.assertNotIn("pull_request_target:", self.text)

    def test_checkout_is_exact_head_and_credential_free(self):
        refs = re.findall(
            r"^\s*(?:-\s*)?uses:\s*([^@\s]+)@([^\s#]+)",
            self.text,
            flags=re.MULTILINE,
        )
        self.assertEqual(refs, [("actions/checkout", CHECKOUT_SHA)])
        expression = (
            "${{ github.event_name == 'pull_request' && "
            "github.event.pull_request.head.sha || github.sha }}"
        )
        self.assertEqual(self.text.count(f"          ref: {expression}"), 1)
        self.assertEqual(self.text.count(f"          EXPECTED_SHA: {expression}"), 1)
        self.assertEqual(self.text.count("          persist-credentials: false"), 1)
        self.assertIn('          test "$(git rev-parse HEAD)" = "$EXPECTED_SHA"', self.text)

    def test_runtime_is_reproducible(self):
        for line in (
            "      LANG: C.UTF-8",
            "      LC_ALL: C.UTF-8",
            '      PYTHONHASHSEED: "1"',
            '      PYTHONNOUSERSITE: "1"',
            '      PYTHONDONTWRITEBYTECODE: "1"',
            "      PYTHONPYCACHEPREFIX: /tmp/raise-observation-template-pyc",
            "      TZ: UTC",
        ):
            with self.subTest(line=line):
                self.assertEqual(self.text.count(line), 1)
        self.assertEqual(self.text.count("    timeout-minutes: 5"), 1)
        self.assertIn(
            'python3 -c \'import platform, sys; '
            'assert platform.python_implementation() == "CPython"; '
            'assert sys.version_info[:2] == (3, 12), sys.version\'',
            self.text,
        )

    def _event_paths(self, event):
        lines = self.text.splitlines()
        start = lines.index(f"  {event}:") + 1
        body = []
        for line in lines[start:]:
            if line and not line.startswith("    "):
                break
            body.append(line)
        self.assertIn("    paths:", body)
        paths_start = body.index("    paths:") + 1
        paths = []
        for line in body[paths_start:]:
            match = re.fullmatch(r'      - "([^"]+)"', line)
            if not match:
                break
            paths.append(match.group(1))
        return paths

    def test_dependencies_and_regressions_are_complete(self):
        expected_paths = [
            "tools/create-physical-observation-template.py",
            "tests/test_physical_observation_template.py",
            "tests/test_observation_template_read_workflow.py",
            ".github/workflows/observation-template-read-integrity.yml",
        ]
        for event in ("push", "pull_request"):
            with self.subTest(event=event):
                self.assertEqual(self._event_paths(event), expected_paths)
        self.assertEqual(
            self.text.count(
                "python3 -m unittest tests.test_physical_observation_template "
                "tests.test_observation_template_read_workflow -v"
            ),
            1,
        )

    def test_run_steps_are_strict_and_worktree_is_clean(self):
        lines = self.text.splitlines()
        step_starts = [
            index for index, line in enumerate(lines)
            if line.startswith("      - name:")
        ]
        run_indices = [
            index for index, line in enumerate(lines)
            if line == "        run: |"
        ]
        self.assertEqual(len(run_indices), 5)
        for run_index in run_indices:
            step_start = max(i for i in step_starts if i < run_index)
            following = [i for i in step_starts if i > step_start]
            step_end = min(following) if following else len(lines)
            step = lines[step_start:step_end]
            self.assertIn("        shell: bash", step)
            self.assertEqual(lines[run_index + 1], "          set -euo pipefail")
        for command in (
            "          git diff --exit-code -- .",
            "          git diff --cached --exit-code -- .",
            '          test -z "$(git ls-files --others --exclude-standard)"',
        ):
            with self.subTest(command=command):
                self.assertEqual(self.text.count(command), 1)


if __name__ == "__main__":
    unittest.main()
