import json
import math
import pathlib
import re
import stat
import subprocess
import tempfile
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
    raw = path.read_bytes()
    if raw.startswith(b"\xef\xbb\xbf"):
        raise ValueError("UTF-8 BOM is not allowed")
    if b"\r" in raw:
        raise ValueError("CR bytes are not allowed; JSON must use LF line endings")
    text = raw.decode("utf-8")
    return json.loads(
        text,
        object_pairs_hook=reject_duplicate_keys,
        parse_constant=reject_nonfinite,
        parse_float=parse_finite_float,
    )


class JsonSurfaceContractTests(unittest.TestCase):
    def setUp(self):
        self.workflow = read_workflow_text(WORKFLOW)

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

    def test_strict_loader_rejects_bom_and_cr_line_endings(self):
        import tempfile

        for payload, message in (
            (b"\xef\xbb\xbf{\"ok\": true}\n", "UTF-8 BOM is not allowed"),
            (b"{\"ok\": true}\r\n", "CR bytes are not allowed"),
        ):
            with self.subTest(message=message):
                with tempfile.TemporaryDirectory() as directory:
                    path = pathlib.Path(directory) / "sample.json"
                    path.write_bytes(payload)
                    with self.assertRaisesRegex(ValueError, message):
                        load_strict_json(path)

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
        self.assertNotRegex(self.workflow, r"(?m)^\s+if:\s*")
        self.assertIn("timeout-minutes: 5", self.workflow)
        self.assertIn("cancel-in-progress: true", self.workflow)
        expression = (
            "${{ github.event_name == 'pull_request' && "
            "github.event.pull_request.head.sha || github.sha }}"
        )
        self.assertEqual(self.workflow.count(expression), 2)
        self.assertIn("persist-credentials: false", self.workflow)
        self.assertEqual(
            self.workflow.count('          test "$(git rev-parse HEAD)" = "$EXPECTED_SHA"'),
            1,
        )

    def test_workflow_trigger_concurrency_and_nested_mappings_are_exact(self):
        lines = self.workflow.splitlines()

        on_start = lines.index("on:") + 1
        permissions_start = lines.index("permissions:")
        events = [
            match.group(1)
            for line in lines[on_start:permissions_start]
            if (match := re.fullmatch(r"  ([A-Za-z0-9_-]+):", line))
        ]
        self.assertEqual(events, ["push", "pull_request"])

        def event_block(event):
            start = lines.index(f"  {event}:") + 1
            block = []
            for line in lines[start:]:
                if line and not line.startswith("    "):
                    break
                block.append(line)
            return block

        push = event_block("push")
        push_keys = [
            match.group(1)
            for line in push
            if (match := re.fullmatch(r"    ([A-Za-z0-9_-]+):", line))
        ]
        self.assertEqual(push_keys, ["branches", "paths"])
        self.assertEqual(push[push.index("    branches:") + 1], "      - main")

        pull_request = event_block("pull_request")
        pr_keys = [
            match.group(1)
            for line in pull_request
            if (match := re.fullmatch(r"    ([A-Za-z0-9_-]+):", line))
        ]
        self.assertEqual(
            pr_keys,
            ["paths"],
            "pull_request must not gain branch/type filters that can skip synchronize validation",
        )

        concurrency_start = lines.index("concurrency:") + 1
        jobs_start = lines.index("jobs:")
        concurrency_keys = [
            match.group(1)
            for line in lines[concurrency_start:jobs_start]
            if (match := re.fullmatch(r"  ([A-Za-z0-9_-]+):.*", line))
        ]
        self.assertEqual(concurrency_keys, ["group", "cancel-in-progress"])

        def step_named(name):
            start = lines.index(f"      - name: {name}")
            following = [
                index for index, line in enumerate(lines)
                if index > start and line.startswith("      - name:")
            ]
            end = min(following) if following else len(lines)
            return lines[start:end]

        checkout = step_named("Checkout exact tested revision")
        with_start = checkout.index("        with:") + 1
        checkout_keys = []
        for line in checkout[with_start:]:
            match = re.fullmatch(r"          ([A-Za-z0-9_-]+):.*", line)
            if match:
                checkout_keys.append(match.group(1))
                continue
            break
        self.assertEqual(checkout_keys, ["ref", "persist-credentials"])

        verifier = step_named("Verify exact tested revision")
        env_start = verifier.index("        env:") + 1
        verifier_keys = []
        for line in verifier[env_start:]:
            match = re.fullmatch(r"          ([A-Za-z0-9_-]+):.*", line)
            if match:
                verifier_keys.append(match.group(1))
                continue
            break
        self.assertEqual(verifier_keys, ["EXPECTED_SHA"])

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
            'raw.startswith(b"\\xef\\xbb\\xbf")',
            'b"\\r" in raw',
            'decode("utf-8")',
            "python3 -m unittest tests.test_json_surface_contract",
            "git diff --exit-code -- .",
            'test -z "$(git ls-files --others --exclude-standard)"',
        ):
            with self.subTest(token=token):
                self.assertIn(token, self.workflow)

    def test_job_environment_surface_is_exact(self):
        lines = self.workflow.splitlines()
        env_start = lines.index("    env:") + 1
        env_keys = []
        for line in lines[env_start:]:
            match = re.fullmatch(r"      ([A-Za-z0-9_-]+):.*", line)
            if match:
                env_keys.append(match.group(1))
                continue
            break

        self.assertEqual(
            env_keys,
            [
                "LANG",
                "LC_ALL",
                "PYTHONHASHSEED",
                "PYTHONNOUSERSITE",
                "PYTHONDONTWRITEBYTECODE",
                "TZ",
            ],
            "JSON workflow environment must not gain unreviewed controls",
        )
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
            "JSON workflow environment values must remain deterministic",
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
            "Validate tracked JSON surface",
            "Run JSON surface regression contract",
            "Verify worktree remains clean",
        ]
        names = [
            lines[index].removeprefix("      - name: ")
            for index in step_starts
        ]
        self.assertEqual(
            names,
            expected_names,
            "JSON workflow must not gain unreviewed steps",
        )

        expected_keys = {
            "Checkout exact tested revision": ["name", "uses", "with"],
            "Verify exact tested revision": ["name", "shell", "env", "run"],
            "Verify Python runtime": ["name", "shell", "run"],
            "Validate tracked JSON surface": ["name", "shell", "run"],
            "Run JSON surface regression contract": ["name", "shell", "run"],
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

    def test_workflow_rejects_quoted_mapping_keys(self):
        quoted_mapping_key = re.compile(
            r'''(?m)^ {0,10}(?:"[A-Za-z0-9_-]+"|'[A-Za-z0-9_-]+')\s*:'''
        )
        fixtures = (
            '        "continue-on-error": true',
            "        'working-directory': /tmp",
            '    "timeout-minutes": 30',
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
            self.workflow,
            quoted_mapping_key,
            "quoted YAML mapping keys can bypass the JSON workflow exact-surface parsers",
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
