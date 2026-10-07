import json
import math
import pathlib
import re
import subprocess
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "json-surface-contract.yml"
EXPECTED_CRITICAL = {
    "app/src/main/assets/raiseai_wear/manifest.json",
    "gateway/package.json",
    "runtime-evidence/ftmo-pr434-runner-recovery-37005843316.json",
    "runtime-evidence/ftmo-pr437-runner-recovery-37006363914.json",
    "runtime-evidence/ftmo-pr439-runner-recovery-37022076400.json",
}


def tracked_json_paths():
    raw = subprocess.check_output(["git", "ls-files", "-z"], cwd=ROOT)
    return sorted(
        item
        for item in raw.decode("utf-8").split("\0")
        if item and pathlib.PurePosixPath(item).suffix.lower() == ".json"
    )


def reject_duplicate_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def reject_nonfinite(value):
    raise ValueError(f"non-finite JSON number: {value}")


def parse_finite_float(value):
    parsed = float(value)
    if not math.isfinite(parsed):
        raise ValueError(f"non-finite JSON number: {value}")
    return parsed


def load_strict_json(path):
    text = path.read_bytes().decode("utf-8")
    return json.loads(
        text,
        object_pairs_hook=reject_duplicate_keys,
        parse_constant=reject_nonfinite,
        parse_float=parse_finite_float,
    )


class JsonSurfaceContractTests(unittest.TestCase):
    def setUp(self):
        self.workflow = WORKFLOW.read_text(encoding="utf-8")

    def test_tracked_json_surface_is_nonempty_and_includes_critical_files(self):
        paths = tracked_json_paths()
        self.assertTrue(paths, "tracked JSON discovery must find files")
        self.assertTrue(
            EXPECTED_CRITICAL.issubset(paths),
            f"critical JSON files missing from discovery: {sorted(EXPECTED_CRITICAL - set(paths))}",
        )

    def test_every_tracked_json_file_is_regular_utf8_and_strict_json(self):
        for relative in tracked_json_paths():
            with self.subTest(path=relative):
                path = ROOT / relative
                self.assertFalse(
                    path.is_symlink(),
                    f"{relative} must be a regular repository file, not a symlink",
                )
                self.assertTrue(path.is_file(), f"{relative} must resolve to a regular file")
                try:
                    load_strict_json(path)
                except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
                    self.fail(f"{relative} must be strict UTF-8 JSON: {exc}")

    def test_strict_loader_rejects_duplicate_keys_and_nonfinite_numbers(self):
        with self.assertRaisesRegex(ValueError, "duplicate JSON key"):
            json.loads(
                '{"a": 1, "a": 2}',
                object_pairs_hook=reject_duplicate_keys,
                parse_constant=reject_nonfinite,
                parse_float=parse_finite_float,
            )
        for token in ("NaN", "Infinity", "-Infinity", "1e400", "-1e400"):
            with self.subTest(token=token):
                with self.assertRaisesRegex(ValueError, "non-finite JSON number"):
                    json.loads(
                        f'{{"value": {token}}}',
                        object_pairs_hook=reject_duplicate_keys,
                        parse_constant=reject_nonfinite,
                        parse_float=parse_finite_float,
                    )

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

    def test_workflow_triggers_cover_current_and_future_json_surfaces(self):
        expected = [
            "*.json",
            "**/*.json",
            "tests/test_json_surface_contract.py",
            ".github/workflows/json-surface-contract.yml",
        ]
        for event in ("push", "pull_request"):
            with self.subTest(event=event):
                self.assertEqual(self._trigger_paths(event), expected)

    def test_workflow_is_hosted_read_only_exact_head_bounded_and_secret_free(self):
        self.assertIn("runs-on: ubuntu-24.04", self.workflow)
        self.assertNotIn("self-hosted", self.workflow)
        self.assertIn("permissions:\n  contents: read\n", self.workflow)
        self.assertNotRegex(self.workflow, r"\$\{\{\s*secrets\.")
        self.assertNotIn("pull_request_target:", self.workflow)
        self.assertNotIn("continue-on-error: true", self.workflow)
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
        self.assertIn(
            "actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1",
            self.workflow,
        )

    def test_workflow_runs_dynamic_strict_json_validation_and_regression(self):
        for token in (
            'subprocess.check_output(["git", "ls-files", "-z"])',
            'pathlib.PurePosixPath(item).suffix.lower() == ".json"',
            "candidate.is_symlink()",
            "tracked JSON files must not be symlinks",
            "object_pairs_hook=reject_duplicate_keys",
            "parse_constant=reject_nonfinite",
            "parse_float=parse_finite_float",
            'decode("utf-8")',
            "python3 -m unittest tests.test_json_surface_contract",
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

    def test_workflow_keeps_exact_top_level_and_job_surfaces(self):
        lines = self.workflow.splitlines()
        top_level = []
        for line in lines:
            match = re.fullmatch(r"([A-Za-z0-9_-]+):.*", line)
            if match:
                top_level.append(match.group(1))
        self.assertEqual(top_level, ["name", "on", "permissions", "concurrency", "jobs"])
        self.assertEqual(lines[0], "name: JSON surface contract CI")

        jobs_block = self.workflow.split("\njobs:\n", 1)[1]
        job_keys = []
        for line in jobs_block.splitlines()[1:]:
            match = re.fullmatch(r"    ([A-Za-z0-9_-]+):.*", line)
            if match:
                job_keys.append(match.group(1))
        self.assertEqual(job_keys, ["runs-on", "timeout-minutes", "env", "steps"])


if __name__ == "__main__":
    unittest.main()
