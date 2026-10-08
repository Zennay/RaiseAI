"""Keep physical acceptance runbook command references executable from repository root.

This deliberately checks only repository-relative launcher/tool paths, not
paths inside the immutable downloaded v1.5.2 carrier or operator home.
"""
import pathlib
import stat
import re
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
RUNBOOK = ROOT / "PHYSICAL-ACCEPTANCE.md"
TOOL = re.compile(r"(?<![\w/])(?:\./)?(tools/[A-Za-z0-9_.-]+\.py|start-frozen-acceptance\.command)(?![\w./-])")


def referenced_local_tools(text):
    # The canonical commands are inside fenced shell examples or inline code.
    # Preserve first-occurrence order while ignoring prose without a tool path.
    return list(dict.fromkeys(TOOL.findall(text)))


def missing_paths(root, paths):
    missing = []
    for path in paths:
        candidate = root / path
        try:
            mode = candidate.lstat().st_mode
        except OSError:
            missing.append(path)
            continue
        if not stat.S_ISREG(mode):
            missing.append(path)
    return missing


class PhysicalRunbookToolReferences(unittest.TestCase):
    def test_current_runbook_references_exist(self):
        references = referenced_local_tools(RUNBOOK.read_text(encoding="utf-8"))
        self.assertIn("start-frozen-acceptance.command", references)
        self.assertIn("tools/validate-physical-observations.py", references)
        self.assertIn("tools/create-physical-observation-template.py", references)
        self.assertEqual([], missing_paths(ROOT, references))

    def test_missing_referenced_script_fails(self):
        with tempfile.TemporaryDirectory() as temp:
            references = referenced_local_tools("python3 tools/absent.py\\nbash ./start-frozen-acceptance.command")
            self.assertEqual(
                ["tools/absent.py", "start-frozen-acceptance.command"],
                missing_paths(pathlib.Path(temp), references),
            )

    def test_symlink_is_not_a_valid_runbook_tool(self):
        with tempfile.TemporaryDirectory() as temp:
            root = pathlib.Path(temp)
            (root / "real.py").write_text("pass\\n", encoding="utf-8")
            (root / "tools").mkdir()
            (root / "tools" / "linked.py").symlink_to(root / "real.py")
            self.assertEqual(["tools/linked.py"], missing_paths(root, ["tools/linked.py"]))

    def test_deduplicates_and_does_not_accept_prefix_only(self):
        self.assertEqual(
            ["tools/validate-physical-observations.py"],
            referenced_local_tools(
                "python3 tools/validate-physical-observations.py\\n"
                "python3 tools/validate-physical-observations.py\\n"
                "tools/validate-physical-observations.py.bak"
            ),
        )


if __name__ == "__main__":
    unittest.main()
