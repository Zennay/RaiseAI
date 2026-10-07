import pathlib
import re
import subprocess
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "python-surface-contract.yml"
EXPECTED_CRITICAL = {
    "tests/test_all_workflow_action_pins.py",
    "tests/test_python_surface_contract.py",
    "tests/test_quality_tooling_workflow.py",
    "tools/validate-physical-observations.py",
}


def tracked_python_paths():
    raw = subprocess.check_output(["git", "ls-files", "-z"], cwd=ROOT)
    return sorted(
        item
        for item in raw.decode("utf-8").split("\0")
        if item and pathlib.PurePosixPath(item).suffix == ".py"
    )


class PythonSurfaceContractTests(unittest.TestCase):
    def setUp(self):
        self.workflow = WORKFLOW.read_text(encoding="utf-8")

    def test_tracked_python_surface_is_nonempty_and_includes_critical_files(self):
        paths = tracked_python_paths()
        self.assertTrue(paths, "tracked Python discovery must find files")
        self.assertTrue(
            EXPECTED_CRITICAL.issubset(paths),
            f"critical Python files missing from discovery: {sorted(EXPECTED_CRITICAL - set(paths))}",
        )

    def test_every_tracked_python_file_is_regular_and_syntax_valid(self):
        for relative in tracked_python_paths():
            with self.subTest(path=relative):
                path = ROOT / relative
                self.assertFalse(
                    path.is_symlink(),
                    f"{relative} must be a regular repository file, not a symlink",
                )
                self.assertTrue(path.is_file(), f"{relative} must resolve to a regular file")
                try:
                    source = path.read_bytes().decode("utf-8")
                    compile(source, relative, "exec", dont_inherit=True)
                except UnicodeDecodeError as exc:
                    self.fail(f"{relative} must be strict UTF-8 Python source: {exc}")
                except (SyntaxError, ValueError) as exc:
                    self.fail(f"{relative} must compile as Python: {exc.__class__.__name__}")

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

    def test_workflow_triggers_cover_current_and_future_python_surfaces(self):
        expected = [
            "*.py",
            "**/*.py",
            ".github/workflows/python-surface-contract.yml",
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

    def test_workflow_uses_only_immutable_checkout_action(self):
        refs = re.findall(
            r"^\s*(?:-\s*)?uses:\s*([^@\s]+)@([^\s#]+)",
            self.workflow,
            flags=re.MULTILINE,
        )
        self.assertEqual([action for action, _ in refs], ["actions/checkout"])
        self.assertRegex(refs[0][1], r"^[0-9a-f]{40}$")

    def test_workflow_runs_dynamic_python_discovery_and_contract(self):
        for token in (
            'subprocess.check_output(["git", "ls-files", "-z"])',
            'pathlib.PurePosixPath(item).suffix == ".py"',
            "candidate.is_symlink()",
            "tracked Python files must not be symlinks",
            "candidate.is_file()",
            'candidate.read_bytes().decode("utf-8")',
            'compile(source, path, "exec", dont_inherit=True)',
            "python3 -m unittest tests.test_python_surface_contract",
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

    def test_workflow_keeps_exact_top_level_and_job_surfaces(self):
        lines = self.workflow.splitlines()
        top_level = []
        for line in lines:
            match = re.fullmatch(r"([A-Za-z0-9_-]+):.*", line)
            if match:
                top_level.append(match.group(1))
        self.assertEqual(
            top_level,
            ["name", "on", "permissions", "concurrency", "jobs"],
        )
        self.assertEqual(lines[0], "name: Python surface contract CI")

        jobs_block = self.workflow.split("\njobs:\n", 1)[1]
        job_keys = []
        for line in jobs_block.splitlines()[1:]:
            match = re.fullmatch(r"    ([A-Za-z0-9_-]+):.*", line)
            if match:
                job_keys.append(match.group(1))
        self.assertEqual(
            job_keys,
            ["runs-on", "timeout-minutes", "env", "steps"],
        )


if __name__ == "__main__":
    unittest.main()
