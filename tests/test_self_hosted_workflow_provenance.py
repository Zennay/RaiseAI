import pathlib
import re
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"
GATE_WORKFLOW = WORKFLOWS / "self-hosted-pr-provenance-quality.yml"
EXACT_HEAD = "${{ github.event_name == 'pull_request' && github.event.pull_request.head.sha || github.sha }}"



def pull_request_self_hosted_candidates():
    workflows = sorted([*WORKFLOWS.glob("*.yml"), *WORKFLOWS.glob("*.yaml")])
    candidates = []
    for path in workflows:
        text = path.read_text(encoding="utf-8")
        if not re.search(r"(?m)^  pull_request:", text):
            continue
        if "runs-on:" not in text:
            continue
        if "self-hosted" not in text or "vps-bb300bba" not in text:
            continue
        candidates.append(path)
    return candidates

def pull_request_self_hosted_workflows():
    workflows = sorted([*WORKFLOWS.glob("*.yml"), *WORKFLOWS.glob("*.yaml")])
    matches = []
    for path in workflows:
        text = path.read_text(encoding="utf-8")
        if not re.search(r"(?m)^  pull_request:", text):
            continue
        runner = re.search(
            r"(?m)^\s+runs-on:\s*\[([^]\n]+)\]\s*$",
            text,
        )
        if runner is None:
            continue
        labels = {label.strip() for label in runner.group(1).split(",")}
        if not {"self-hosted", "vps-bb300bba"}.issubset(labels):
            continue
        matches.append((path, text))
    return matches


def pull_request_target_self_hosted_workflows():
    workflows = sorted([*WORKFLOWS.glob("*.yml"), *WORKFLOWS.glob("*.yaml")])
    matches = []
    for path in workflows:
        text = path.read_text(encoding="utf-8")
        if not re.search(r"(?m)^  pull_request_target:", text):
            continue
        if "self-hosted" not in text or "vps-bb300bba" not in text:
            continue
        matches.append(path)
    return matches


class SelfHostedWorkflowProvenanceTests(unittest.TestCase):
    def test_self_hosted_pr_workflows_exist(self):
        workflows = pull_request_self_hosted_workflows()
        self.assertTrue(
            workflows,
            "expected at least one self-hosted pull-request workflow on vps-bb300bba",
        )

    def test_self_hosted_pr_runner_declarations_cannot_escape_discovery(self):
        candidates = pull_request_self_hosted_candidates()
        discovered = [path for path, _ in pull_request_self_hosted_workflows()]
        self.assertEqual(
            discovered,
            candidates,
            "every pull-request workflow naming the VPS self-hosted labels must use the canonical inline runs-on list",
        )

    def test_self_hosted_pr_checkouts_are_exact_head_bound(self):
        workflows = pull_request_self_hosted_workflows()
        for path, text in workflows:
            with self.subTest(workflow=path.name):
                lines = text.splitlines()
                checkout_indices = [
                    index
                    for index, line in enumerate(lines)
                    if re.match(
                        r"^\s*(?:-\s*)?uses:\s*actions/checkout@",
                        line,
                    )
                ]
                self.assertTrue(
                    checkout_indices,
                    "self-hosted PR validation must checkout an exact repository revision",
                )
                for checkout_index in checkout_indices:
                    following_step = next(
                        (
                            index
                            for index, line in enumerate(
                                lines[checkout_index + 1 :],
                                checkout_index + 1,
                            )
                            if line.startswith("      - ")
                        ),
                        len(lines),
                    )
                    checkout_step = lines[checkout_index:following_step]
                    with self.subTest(
                        workflow=path.name,
                        checkout_line=checkout_index + 1,
                    ):
                        self.assertIn(
                            f"          ref: {EXACT_HEAD}",
                            checkout_step,
                            "checkout must select the PR head instead of GitHub's synthetic merge ref",
                        )
                        self.assertIn(
                            "          persist-credentials: false",
                            checkout_step,
                            "checkout must not persist repository credentials",
                        )
                self.assertIn(
                    "git rev-parse HEAD",
                    text,
                    "workflow must verify the revision that actually reached the runner",
                )

    def test_pull_request_target_cannot_escape_self_hosted_guard(self):
        self.assertEqual(
            pull_request_target_self_hosted_workflows(),
            [],
            "pull_request_target must never be able to execute on vps-bb300bba",
        )

    def test_self_hosted_pr_workflows_are_bounded_and_secret_free(self):
        workflows = pull_request_self_hosted_workflows()
        for path, text in workflows:
            with self.subTest(workflow=path.name):
                self.assertNotRegex(
                    text,
                    r"\$\{\{\s*secrets\.",
                    "self-hosted PR validation must not consume repository secrets",
                )
                self.assertNotRegex(
                    text,
                    r"(?m)^\s*environment\s*:",
                    "self-hosted PR validation must not bind a deployment environment",
                )
                timeouts = [
                    int(value)
                    for value in re.findall(
                        r"(?m)^\s+timeout-minutes:\s*([0-9]+)\s*$",
                        text,
                    )
                ]
                self.assertTrue(
                    timeouts,
                    "every self-hosted PR workflow must have a bounded timeout",
                )
                self.assertTrue(
                    all(0 < value <= 30 for value in timeouts),
                    "self-hosted PR validation timeouts must stay within 30 minutes",
                )


    def test_dedicated_provenance_gate_is_read_only(self):
        text = GATE_WORKFLOW.read_text(encoding="utf-8")
        permissions = re.search(
            r"(?ms)^permissions:\n((?:  [^\n]+\n)+)",
            text,
        )
        self.assertIsNotNone(permissions)
        self.assertEqual(
            permissions.group(1).splitlines(),
            ["  contents: read"],
            "the dedicated provenance gate must remain read-only",
        )
        self.assertNotRegex(text, r"(?m)^    permissions:")



if __name__ == "__main__":
    unittest.main()
