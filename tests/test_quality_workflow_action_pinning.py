import re
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = (
    REPO_ROOT / ".github/workflows/watch-app-test.yml",
    REPO_ROOT / ".github/workflows/physical-quality-evidence-test.yml",
)
PINNED_ACTION = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+@[0-9a-f]{40}$")


class QualityWorkflowActionPinningTest(unittest.TestCase):
    def test_external_actions_are_immutable_sha_pinned(self):
        violations = []
        for workflow in WORKFLOWS:
            for line_number, raw in enumerate(workflow.read_text().splitlines(), start=1):
                stripped = raw.strip()
                if not stripped.startswith("uses: "):
                    continue
                value = stripped.removeprefix("uses: ").split(" #", 1)[0].strip()
                if value.startswith("./") or value.startswith("docker://"):
                    continue
                if not PINNED_ACTION.fullmatch(value):
                    violations.append(f"{workflow.relative_to(REPO_ROOT)}:{line_number}: {value}")

        self.assertEqual([], violations, "Unpinned external actions:\n" + "\n".join(violations))


if __name__ == "__main__":
    unittest.main()
