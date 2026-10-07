import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "release-documentation-identity.yml"
CHECKOUT_SHA = "3d3c42e5aac5ba805825da76410c181273ba90b1"  # v7.0.1, node24
EXPECTED_TRIGGER_PATHS = [
    "VERSION.txt",
    "app/build.gradle.kts",
    "README.md",
    "START-HERE.md",
    "PHYSICAL-ACCEPTANCE.md",
    "start-frozen-acceptance.command",
    "start-physical-handoff.command",
    "tools/fetch-frozen-physical-handoff.py",
    "tools/create-physical-observation-template.py",
    "tools/validate-physical-observations.py",
    "DEVICE-TEST.md",
    "REMOTE-LOGIN.md",
    "GEMINI-HOME-SETUP.md",
    "CHATGPT-WEB-SETUP.md",
    "tests/test_release_documentation_identity.py",
    "tests/test_release_documentation_workflow.py",
    ".github/workflows/release-documentation-identity.yml",
]


class ReleaseDocumentationWorkflowContractTests(unittest.TestCase):
    def setUp(self):
        self.text = WORKFLOW.read_text(encoding="utf-8")

    def test_hosted_python_runtime_is_reproducible(self):
        for line in (
            "      LANG: C.UTF-8",
            "      LC_ALL: C.UTF-8",
            '      PYTHONHASHSEED: "1"',
            '      PYTHONNOUSERSITE: "1"',
            '      PYTHONDONTWRITEBYTECODE: "1"',
            "      PYTHONPYCACHEPREFIX: /tmp/raise-release-doc-pyc",
            "      TZ: UTC",
        ):
            with self.subTest(line=line):
                self.assertEqual(self.text.count(line), 1)

        runtime = (
            '          python3 -c \'import platform, sys; '
            'assert platform.python_implementation() == "CPython"; '
            'assert sys.version_info[:2] == (3, 12), sys.version\''
        )
        self.assertEqual(self.text.count(runtime), 1)
        self.assertEqual(self.text.count("    runs-on: ubuntu-24.04"), 1)
        self.assertNotIn("ubuntu-latest", self.text)

    def test_external_action_surface_is_exact_and_immutable(self):
        refs = re.findall(
            r"^\s*(?:-\s*)?uses:\s*([^@\s]+)@([^\s#]+)",
            self.text,
            flags=re.MULTILINE,
        )
        self.assertEqual(refs, [("actions/checkout", CHECKOUT_SHA)])
        self.assertRegex(refs[0][1], r"^[0-9a-f]{40}$")
        self.assertIn(
            f"uses: actions/checkout@{CHECKOUT_SHA} # v7.0.1 (node24)",
            self.text,
        )

    def test_checkout_is_exact_head_and_credential_free(self):
        expression = "${{ github.event.pull_request.head.sha || github.sha }}"
        self.assertEqual(self.text.count(f"          ref: {expression}"), 1)
        self.assertEqual(
            self.text.count(f"          EXPECTED_SHA: {expression}"),
            1,
        )
        self.assertEqual(self.text.count("          persist-credentials: false"), 1)
        self.assertIn('          test "$(git rev-parse HEAD)" = "$EXPECTED_SHA"', self.text)

    def test_permissions_are_exactly_read_only(self):
        block = re.search(
            r"(?ms)^permissions:\n((?:  [^\n]+\n)+)",
            self.text,
        )
        self.assertIsNotNone(block)
        self.assertEqual(block.group(1).splitlines(), ["  contents: read"])
        self.assertNotRegex(self.text, r"(?m)^    permissions:")

    def _event_paths(self, event):
        lines = self.text.splitlines()
        start = lines.index(f"  {event}:") + 1
        body = []
        for line in lines[start:]:
            if line and not line.startswith("    "):
                break
            body.append(line)
        self.assertIn("    paths:", body)
        paths_start = body.index("    paths:") + 1
        paths = []
        for line in body[paths_start:]:
            match = re.fullmatch(r'      - "([^"]+)"', line)
            if not match:
                break
            paths.append(match.group(1))
        return paths

    def test_push_and_pull_request_dependencies_match_exact_contract(self):
        for event in ("push", "pull_request"):
            with self.subTest(event=event):
                self.assertEqual(self._event_paths(event), EXPECTED_TRIGGER_PATHS)

    def test_contract_test_executes_in_the_release_lane(self):
        self.assertEqual(
            self.text.count("python3 -m unittest tests.test_release_documentation_identity tests.test_release_documentation_workflow"),
            1,
        )

    def test_run_steps_fail_closed_under_bash(self):
        lines = self.text.splitlines()
        step_starts = [
            index
            for index, line in enumerate(lines)
            if line.startswith("      - name:")
        ]
        run_indices = [
            index
            for index, line in enumerate(lines)
            if line == "        run: |"
        ]
        self.assertTrue(run_indices)
        self.assertNotIn("continue-on-error: true", self.text)
        for run_index in run_indices:
            with self.subTest(line=run_index + 1):
                step_start = max(i for i in step_starts if i < run_index)
                following = [i for i in step_starts if i > step_start]
                step_end = min(following) if following else len(lines)
                step = lines[step_start:step_end]
                self.assertIn("        shell: bash", step)
                self.assertEqual(lines[run_index + 1], "          set -euo pipefail")

    def test_workflow_is_bounded_hosted_and_secret_free(self):
        self.assertIn("runs-on: ubuntu-24.04", self.text)
        self.assertIn("timeout-minutes: 5", self.text)
        self.assertNotIn("self-hosted", self.text)
        self.assertNotIn("pull_request_target:", self.text)
        self.assertNotRegex(self.text, r"\$\{\{\s*secrets\.")

    def test_workflow_keeps_exact_top_level_and_job_surfaces(self):
        lines = self.text.splitlines()
        top_level = [
            match.group(1)
            for line in lines
            if (match := re.fullmatch(r"([A-Za-z0-9_-]+):.*", line))
        ]
        self.assertEqual(
            top_level,
            ["name", "on", "permissions", "concurrency", "jobs"],
        )
        self.assertEqual(lines[0], "name: Release documentation identity contract")

        jobs_block = self.text.split("\njobs:\n", 1)[1]
        job_keys = [
            match.group(1)
            for line in jobs_block.splitlines()[1:]
            if (match := re.fullmatch(r"    ([A-Za-z0-9_-]+):.*", line))
        ]
        self.assertEqual(
            job_keys,
            ["runs-on", "timeout-minutes", "env", "steps"],
            "release documentation workflow must not gain unreviewed job controls",
        )

    def test_trigger_concurrency_and_env_surfaces_are_exact(self):
        lines = self.text.splitlines()

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
            "pull_request must not gain filters that can skip synchronize validation",
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
                "PYTHONPYCACHEPREFIX",
                "TZ",
            ],
            "release documentation workflow environment must not gain unreviewed controls",
        )

    def test_step_and_nested_mapping_surfaces_are_exact(self):
        lines = self.text.splitlines()
        step_starts = [
            index
            for index, line in enumerate(lines)
            if line.startswith("      - name:")
        ]
        expected_names = [
            "Checkout exact tested revision",
            "Verify exact tested revision",
            "Verify Python runtime",
            "Run release documentation identity contract",
            "Verify worktree remains clean",
        ]
        names = [lines[index].removeprefix("      - name: ") for index in step_starts]
        self.assertEqual(
            names,
            expected_names,
            "release documentation workflow must not gain unreviewed steps",
        )

        expected_keys = {
            "Checkout exact tested revision": ["name", "uses", "with"],
            "Verify exact tested revision": ["name", "shell", "env", "run"],
            "Verify Python runtime": ["name", "shell", "run"],
            "Run release documentation identity contract": ["name", "shell", "run"],
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
