import pathlib
import re
import subprocess
import tempfile
import unittest
from urllib.parse import unquote, urlsplit


ROOT = pathlib.Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "markdown-surface-contract.yml"
EXPECTED_CRITICAL = {
    "README.md",
    "START-HERE.md",
    "PHYSICAL-ACCEPTANCE.md",
    "gateway/README.md",
}
LINK_RE = re.compile(r"\]\(([^)\n]+)\)")
BACKTICK_FENCE = chr(96) * 3


class MarkdownContractError(ValueError):
    pass


def tracked_markdown_paths():
    raw = subprocess.check_output(["git", "ls-files", "-z"], cwd=ROOT)
    return sorted(
        item
        for item in raw.decode("utf-8").split("\0")
        if item and pathlib.PurePosixPath(item).suffix.lower() == ".md"
    )


def decode_markdown_source(raw: bytes, *, relative: str) -> str:
    if b"\x00" in raw:
        raise MarkdownContractError(f"{relative} must not contain NUL bytes")
    if b"\r" in raw:
        raise MarkdownContractError(
            f"{relative} must use LF line endings without carriage returns"
        )
    try:
        return raw.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise MarkdownContractError(f"{relative} must be strict UTF-8") from exc


def prose_without_fenced_code(text: str) -> str:
    output = []
    fence = None
    for line in text.splitlines():
        stripped = line.lstrip()
        marker = None
        if stripped.startswith(BACKTICK_FENCE):
            marker = BACKTICK_FENCE
        elif stripped.startswith("~~~"):
            marker = "~~~"

        if marker:
            if fence is None:
                fence = marker
            elif fence == marker:
                fence = None
            continue

        if fence is None:
            output.append(line)
    return "\n".join(output)


def local_link_target(document: pathlib.Path, raw_target: str, *, root: pathlib.Path):
    target = raw_target.strip()
    if target.startswith("<") and ">" in target:
        target = target[1 : target.index(">")].strip()
    else:
        target = target.split(maxsplit=1)[0] if target else ""

    if not target or target.startswith("#") or target.startswith("/") or target.startswith("//"):
        return None

    parsed = urlsplit(target)
    if parsed.scheme or parsed.netloc:
        return None

    relative_path = unquote(parsed.path)
    if not relative_path:
        return None

    root_resolved = root.resolve()
    unresolved = document.parent / relative_path
    candidate = unresolved.resolve(strict=False)
    try:
        candidate.relative_to(root_resolved)
    except ValueError as exc:
        raise MarkdownContractError(
            f"{document.relative_to(root)}: local link escapes repository: {raw_target}"
        ) from exc

    if unresolved.is_symlink():
        raise MarkdownContractError(
            f"{document.relative_to(root)}: local link target must not be a symlink: {raw_target}"
        )
    if not candidate.exists():
        raise MarkdownContractError(
            f"{document.relative_to(root)}: local link target does not exist: {raw_target}"
        )
    if candidate.is_symlink():
        raise MarkdownContractError(
            f"{document.relative_to(root)}: local link target must not be a symlink: {raw_target}"
        )
    return candidate


def validate_document(relative: str, *, root: pathlib.Path = ROOT):
    path = root / relative
    if path.is_symlink() or not path.is_file():
        raise MarkdownContractError(f"{relative} must be a regular repository file")

    text = decode_markdown_source(path.read_bytes(), relative=relative)
    prose = prose_without_fenced_code(text)
    for match in LINK_RE.finditer(prose):
        local_link_target(path, match.group(1), root=root)


class MarkdownSurfaceContractTests(unittest.TestCase):
    def setUp(self):
        self.workflow = WORKFLOW.read_text(encoding="utf-8")

    def test_tracked_markdown_surface_is_nonempty_and_includes_critical_docs(self):
        paths = tracked_markdown_paths()
        self.assertTrue(paths, "tracked Markdown discovery must find documentation")
        self.assertTrue(
            EXPECTED_CRITICAL.issubset(paths),
            f"critical Markdown files missing: {sorted(EXPECTED_CRITICAL - set(paths))}",
        )

    def test_every_tracked_markdown_file_is_reviewable_and_local_links_resolve(self):
        for relative in tracked_markdown_paths():
            with self.subTest(path=relative):
                validate_document(relative)

    def test_link_parser_skips_external_anchor_and_fenced_examples(self):
        with tempfile.TemporaryDirectory(prefix="raiseai-markdown-") as temporary:
            root = pathlib.Path(temporary)
            docs = root / "docs"
            docs.mkdir()
            (root / "target.md").write_text("# target\n", encoding="utf-8")
            document = docs / "guide.md"
            document.write_text(
                "[ok](../target.md#section)\n"
                "[external](https://example.com/docs)\n"
                "[anchor](#local-section)\n"
                "~~~md\n[example](missing.md)\n~~~\n"
                f"{BACKTICK_FENCE}md\n[example](also-missing.md)\n{BACKTICK_FENCE}\n",
                encoding="utf-8",
            )
            validate_document("docs/guide.md", root=root)

    def test_link_parser_rejects_missing_and_escaping_targets(self):
        with tempfile.TemporaryDirectory(prefix="raiseai-markdown-") as temporary:
            root = pathlib.Path(temporary)
            docs = root / "docs"
            docs.mkdir()
            document = docs / "guide.md"
            document.write_text("[missing](missing.md)\n", encoding="utf-8")
            with self.assertRaisesRegex(MarkdownContractError, "does not exist"):
                validate_document("docs/guide.md", root=root)

            outside = root.parent / f"{root.name}-outside.md"
            outside.write_text("# outside\n", encoding="utf-8")
            try:
                document.write_text(f"[escape](../../{outside.name})\n", encoding="utf-8")
                with self.assertRaisesRegex(MarkdownContractError, "escapes repository"):
                    validate_document("docs/guide.md", root=root)
            finally:
                outside.unlink(missing_ok=True)

    def test_link_parser_rejects_direct_symlink_target(self):
        with tempfile.TemporaryDirectory(prefix="raiseai-markdown-") as temporary:
            root = pathlib.Path(temporary)
            docs = root / "docs"
            docs.mkdir()
            target = root / "target.md"
            target.write_text("# target\n", encoding="utf-8")
            alias = root / "alias.md"
            alias.symlink_to(target)
            document = docs / "guide.md"
            document.write_text("[alias](../alias.md)\n", encoding="utf-8")
            with self.assertRaisesRegex(MarkdownContractError, "must not be a symlink"):
                validate_document("docs/guide.md", root=root)

    def test_markdown_source_rejects_crlf_nul_and_non_utf8(self):
        fixtures = (
            (b"# title\r\n", "LF line endings"),
            (b"# title\x00\n", "NUL bytes"),
            (b"# title\n\xff", "strict UTF-8"),
        )
        for payload, message in fixtures:
            with self.subTest(message=message):
                with self.assertRaisesRegex(MarkdownContractError, message):
                    decode_markdown_source(payload, relative="fixture.md")

    def test_workflow_is_self_hosted_read_only_exact_head_and_bounded(self):
        self.assertIn("runs-on: [self-hosted, linux, x64, vps-bb300bba]", self.workflow)
        self.assertIn("permissions:\n  contents: read\n", self.workflow)
        self.assertIn("timeout-minutes: 5", self.workflow)
        self.assertIn("cancel-in-progress: true", self.workflow)
        self.assertNotRegex(self.workflow, r"\$\{\{\s*secrets\.")
        expression = (
            "${{ github.event_name == 'pull_request' && "
            "github.event.pull_request.head.sha || github.sha }}"
        )
        self.assertEqual(self.workflow.count(expression), 2)
        self.assertIn("persist-credentials: false", self.workflow)

    def test_workflow_triggers_cover_markdown_contract_surface(self):
        for token in (
            '"**/*.md"',
            '"tests/test_markdown_surface_contract.py"',
            '".github/workflows/markdown-surface-contract.yml"',
            "python3 -m unittest tests.test_markdown_surface_contract",
            "git diff --exit-code -- .",
            'test -z "$(git ls-files --others --exclude-standard)"',
        ):
            with self.subTest(token=token):
                self.assertIn(token, self.workflow)

    def test_workflow_uses_only_immutable_checkout_action(self):
        refs = re.findall(
            r"^\s*(?:-\s*)?uses:\s*([^@\s]+)@([^\s#]+)",
            self.workflow,
            flags=re.MULTILINE,
        )
        self.assertEqual([action for action, _ in refs], ["actions/checkout"])
        self.assertRegex(refs[0][1], r"^[0-9a-f]{40}$")

    def test_all_run_steps_are_strict_bash(self):
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


if __name__ == "__main__":
    unittest.main()
