import pathlib
import re
import subprocess
import unittest
import xml.etree.ElementTree as ET


ROOT = pathlib.Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "xml-surface-contract.yml"
EXPECTED_CRITICAL = {
    "app/src/main/AndroidManifest.xml",
    "app/src/main/res/drawable/ic_raise_ai.xml",
    "app/src/main/res/values/colors.xml",
    "app/src/main/res/values/styles.xml",
}
FORBIDDEN_DECLARATIONS = ("<!DOCTYPE", "<!ENTITY")
UTF8_BOM = b"\xef\xbb\xbf"


def tracked_xml_paths():
    raw = subprocess.check_output(["git", "ls-files", "-z"], cwd=ROOT)
    return sorted(
        item
        for item in raw.decode("utf-8").split("\0")
        if item and pathlib.PurePosixPath(item).suffix.lower() == ".xml"
    )


def decode_canonical_xml_source(data: bytes, *, relative: str) -> str:
    if data.startswith(UTF8_BOM):
        raise ValueError(f"{relative} must not start with a UTF-8 BOM")
    if b"\x00" in data:
        raise ValueError(f"{relative} must not contain NUL bytes")
    if b"\r" in data:
        raise ValueError(f"{relative} must use LF-only line endings")
    try:
        return data.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise ValueError(f"{relative} must be strict UTF-8 XML") from exc


class XmlSurfaceContractTests(unittest.TestCase):
    def setUp(self):
        self.workflow = WORKFLOW.read_text(encoding="utf-8")

    def test_tracked_xml_surface_is_nonempty_and_includes_critical_android_files(self):
        paths = tracked_xml_paths()
        self.assertTrue(paths, "tracked XML discovery must find files")
        self.assertTrue(
            EXPECTED_CRITICAL.issubset(paths),
            f"critical Android XML missing from discovery: {sorted(EXPECTED_CRITICAL - set(paths))}",
        )

    def test_every_tracked_xml_file_is_regular_safe_and_well_formed(self):
        for relative in tracked_xml_paths():
            with self.subTest(path=relative):
                path = ROOT / relative
                self.assertFalse(
                    path.is_symlink(),
                    f"{relative} must be a regular repository file, not a symlink",
                )
                self.assertTrue(path.is_file(), f"{relative} must resolve to a regular file")
                data = path.read_bytes()
                try:
                    text = decode_canonical_xml_source(data, relative=relative)
                except ValueError as exc:
                    self.fail(str(exc))
                upper = text.upper()
                for declaration in FORBIDDEN_DECLARATIONS:
                    self.assertNotIn(
                        declaration,
                        upper,
                        f"{relative} must not contain DTD/entity declarations",
                    )
                try:
                    ET.fromstring(text)
                except ET.ParseError as exc:
                    self.fail(f"{relative} must be well-formed XML: {exc}")

    def test_canonical_xml_decoder_rejects_bom_cr_nul_and_invalid_utf8(self):
        with self.assertRaisesRegex(ValueError, "UTF-8 BOM"):
            decode_canonical_xml_source(
                UTF8_BOM + b'<?xml version="1.0"?><root/>\n',
                relative="fixture.xml",
            )
        for payload in (
            b'<?xml version="1.0"?><root/>\r\n',
            b'<?xml version="1.0"?><root/>\r',
        ):
            with self.subTest(payload=payload):
                with self.assertRaisesRegex(ValueError, "LF-only line endings"):
                    decode_canonical_xml_source(payload, relative="fixture.xml")
        with self.assertRaisesRegex(ValueError, "NUL bytes"):
            decode_canonical_xml_source(b"<root>\x00</root>\n", relative="fixture.xml")
        with self.assertRaisesRegex(ValueError, "strict UTF-8 XML"):
            decode_canonical_xml_source(b"<root>\xff</root>\n", relative="fixture.xml")

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

    def test_workflow_triggers_cover_current_and_future_xml_surfaces(self):
        expected = [
            "*.xml",
            "**/*.xml",
            "tests/test_xml_surface_contract.py",
            ".github/workflows/xml-surface-contract.yml",
        ]
        for event in ("push", "pull_request"):
            with self.subTest(event=event):
                self.assertEqual(self._trigger_paths(event), expected)

    def test_workflow_is_hosted_read_only_exact_head_bounded_and_secret_free(self):
        self.assertIn("runs-on: ubuntu-24.04", self.workflow)
        self.assertNotIn("self-hosted", self.workflow)
        self.assertIn("permissions:\n  contents: read\n", self.workflow)
        self.assertNotRegex(self.workflow, r"\$\{\{\s*secrets\.")
        self.assertNotRegex(self.workflow, r"^\s*environment\s*:", msg="must not use deployment environments")
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

    def test_workflow_runs_dynamic_xml_validation_and_regression(self):
        for token in (
            'subprocess.check_output(["git", "ls-files", "-z"])',
            'pathlib.PurePosixPath(item).suffix.lower() == ".xml"',
            "candidate.is_symlink()",
            "tracked XML files must not be symlinks",
            'FORBIDDEN_DECLARATIONS = ("<!DOCTYPE", "<!ENTITY")',
            'UTF8_BOM = b"\\xef\\xbb\\xbf"',
            "if data.startswith(UTF8_BOM):",
            'if b"\\x00" in data:',
            'if b"\\r" in data:',
            'data.decode("utf-8", errors="strict")',
            "ET.fromstring(text)",
            "python3 -m unittest tests.test_xml_surface_contract",
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
        self.assertEqual(
            top_level,
            ["name", "on", "permissions", "concurrency", "jobs"],
        )
        self.assertEqual(lines[0], "name: XML surface contract CI")

        jobs_block = self.workflow.split("\njobs:\n", 1)[1]
        job_keys = []
        for line in jobs_block.splitlines()[1:]:
            match = re.fullmatch(r"    ([A-Za-z0-9_-]+):.*", line)
            if match:
                job_keys.append(match.group(1))
        self.assertEqual(job_keys, ["runs-on", "timeout-minutes", "env", "steps"])


    def test_workflow_trigger_concurrency_and_env_surfaces_are_exact(self):
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
        self.assertEqual(
            [
                match.group(1)
                for line in push
                if (match := re.fullmatch(r"    ([A-Za-z0-9_-]+):", line))
            ],
            ["branches", "paths"],
        )
        branches_start = push.index("    branches:") + 1
        self.assertEqual(push[branches_start], "      - main")

        pull_request = event_block("pull_request")
        self.assertEqual(
            [
                match.group(1)
                for line in pull_request
                if (match := re.fullmatch(r"    ([A-Za-z0-9_-]+):", line))
            ],
            ["paths"],
            "pull_request must not gain type or branch filters that can skip synchronize validation",
        )

        concurrency_start = lines.index("concurrency:") + 1
        jobs_start = lines.index("jobs:")
        self.assertEqual(
            [
                match.group(1)
                for line in lines[concurrency_start:jobs_start]
                if (match := re.fullmatch(r"  ([A-Za-z0-9_-]+):.*", line))
            ],
            ["group", "cancel-in-progress"],
        )

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
            "XML parser environment must not gain unreviewed interpreter controls",
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
            "XML parser environment values must remain deterministic",
        )

    def test_workflow_step_and_nested_mapping_surfaces_are_exact(self):
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
            "Validate tracked XML surface",
            "Run XML surface regression contract",
            "Verify worktree remains clean",
        ]
        self.assertEqual(
            [lines[index].removeprefix("      - name: ") for index in step_starts],
            expected_names,
            "XML surface workflow must not gain unreviewed steps",
        )

        expected_keys = {
            "Checkout exact tested revision": ["name", "uses", "with"],
            "Verify exact tested revision": ["name", "shell", "env", "run"],
            "Verify Python runtime": ["name", "shell", "run"],
            "Validate tracked XML surface": ["name", "shell", "run"],
            "Run XML surface regression contract": ["name", "shell", "run"],
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
            self.assertEqual(keys, expected_keys[name])

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


if __name__ == "__main__":
    unittest.main()
