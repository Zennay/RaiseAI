import pathlib
import re
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"


class AllWorkflowActionPinsTests(unittest.TestCase):
    def test_every_remote_uses_ref_is_immutable(self):
        workflows = sorted(WORKFLOWS.glob("*.yml"))
        self.assertTrue(workflows, "repository must retain GitHub Actions workflows")

        remote_refs = []
        for workflow in workflows:
            text = workflow.read_text(encoding="utf-8")
            for match in re.finditer(
                r"^\s*(?:-\s*)?uses:\s*([^\s#]+)",
                text,
                flags=re.MULTILINE,
            ):
                value = match.group(1)
                if value.startswith("./") or value.startswith("docker://"):
                    continue
                remote_refs.append((workflow.name, value))

        self.assertTrue(remote_refs, "repository must retain at least one remote action")
        for workflow, value in remote_refs:
            with self.subTest(workflow=workflow, uses=value):
                action, separator, ref = value.rpartition("@")
                self.assertEqual(
                    separator,
                    "@",
                    f"{workflow}: remote uses ref must include an immutable revision",
                )
                self.assertTrue(
                    action,
                    f"{workflow}: remote uses ref must name an action or reusable workflow",
                )
                self.assertRegex(
                    ref,
                    r"^[0-9a-f]{40}$",
                    f"{workflow}: {value} must use an immutable 40-character commit SHA",
                )


if __name__ == "__main__":
    unittest.main()
