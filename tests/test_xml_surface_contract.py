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


if __name__ == "__main__":
    unittest.main()
