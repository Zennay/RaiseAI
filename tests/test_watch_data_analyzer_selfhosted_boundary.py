import pathlib
import re
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "watch-data-analyzer-quality.yml"
FORK_GUARD = (
    "    if: ${{ github.event_name != 'pull_request' || "
    "github.event.pull_request.head.repo.full_name == github.repository }}"
)
SELF = "tests/test_watch_data_analyzer_selfhosted_boundary.py"


class WatchDataAnalyzerSelfHostedBoundaryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.workflow = WORKFLOW.read_text(encoding="utf-8")

    def test_fork_pull_requests_are_rejected_before_runner_allocation(self):
        self.assertEqual(self.workflow.count(FORK_GUARD), 1)
        self.assertEqual(
            len(re.findall(r"(?m)^\s*if\s*:", self.workflow)),
            1,
            "the same-repository fork guard must be the only workflow if surface",
        )
        self.assertLess(
            self.workflow.index(FORK_GUARD),
            self.workflow.index(
                "    runs-on: [self-hosted, linux, x64, vps-bb300bba]"
            ),
            "the trust guard must be job-level so forks are skipped before runner allocation",
        )

    def test_trust_boundary_keeps_safe_trigger_and_token_contracts(self):
        self.assertIn("  pull_request:\n", self.workflow)
        self.assertIn("  push:\n", self.workflow)
        self.assertNotIn("pull_request_target:", self.workflow)
        self.assertIn("permissions:\n  contents: read\n", self.workflow)
        self.assertNotIn("${{ secrets.", self.workflow)
        self.assertIn("          persist-credentials: false", self.workflow)

    def test_python_runtime_isolated_and_boundary_test_self_validates(self):
        for line in (
            "      LANG: C.UTF-8",
            "      LC_ALL: C.UTF-8",
            '      PYTHONHASHSEED: "1"',
            '      PYTHONDONTWRITEBYTECODE: "1"',
            '      PYTHONNOUSERSITE: "1"',
            "      TZ: UTC",
        ):
            with self.subTest(line=line):
                self.assertEqual(self.workflow.count(line), 1)
        self.assertEqual(
            self.workflow.count(
                'python3 -c \'import platform, sys; assert platform.python_implementation() == "CPython"; '
                'assert sys.version_info[:2] == (3, 12), sys.version\''
            ),
            1,
        )
        self.assertEqual(
            self.workflow.count(f'      - "{SELF}"'),
            2,
            "the boundary contract must trigger both push and pull_request validation",
        )
        self.assertIn(
            f"          python3 -m unittest {SELF} -v",
            self.workflow,
        )


if __name__ == "__main__":
    unittest.main()
