from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"

LEGACY_FOREIGN_WORKFLOWS = {
    "cancel-stale-zcloud-recovery-hosted.yml",
    "ftmo-pr434-runner-recovery.yml",
    "ftmo-pr437-runner-recovery.yml",
    "ftmo-pr439-runner-recovery.yml",
    "ftmo-pr472-telemetry-proof.yml",
    "lightup-pr13-exact-head-proof-20261005.yml",
    "lightup-pr17-exact-head-proof-20261005.yml",
    "lightup-pr21-exact-head-proof-20261005.yml",
    "probe-zcloud-dashboard-external.yml",
    "recover-zcloud-dashboard-20261004.yml",
    "zcloud-emergency-queue-preempt-20261006.yml",
    "zcloud-emergency-restore-20261006.yml",
    "zcloud-listener-recovery-20261004.yml",
    "zcloud-public-dashboard-probe-20261004.yml",
    "zcloud-public-dashboard-recovery-20261004.yml",
    "zcloud-public-verify-now-20261006.yml",
    "zcloud-rollout-queue-cleanup-20261004.yml",
    "zcloud-runtime-worker-recovery-20261004.yml",
    "zcloud-workers-live-recovery-20261006.yml",
}

FOREIGN_MARKER_RE = re.compile(r"(?i)\b(?:ftmo|lightup|zcloud)\b")
ON_KEY = r"""(?:"on"|'on'|on)"""
PULL_REQUEST_KEY = r"""(?:"pull_request"|'pull_request'|pull_request)"""
PULL_REQUEST_BLOCK_RE = re.compile(rf"(?m)^\s{{0,2}}{PULL_REQUEST_KEY}\s*:")
PULL_REQUEST_FLOW_MAP_RE = re.compile(
    rf"(?m)^\s{{0,2}}{ON_KEY}\s*:\s*\{{[^}}\n]*{PULL_REQUEST_KEY}\s*:"
)
PULL_REQUEST_FLOW_SEQUENCE_RE = re.compile(
    rf"(?ms)^\s{{0,2}}{ON_KEY}\s*:\s*\[[^\]]*{PULL_REQUEST_KEY}(?:\s*,|\s*\])"
)


def is_foreign_workflow_name(name: str) -> bool:
    return FOREIGN_MARKER_RE.search(name) is not None


def foreign_workflows() -> list[Path]:
    return sorted(
        path
        for path in WORKFLOWS.iterdir()
        if path.is_file()
        and path.suffix in {".yml", ".yaml"}
        and (
            path.name in LEGACY_FOREIGN_WORKFLOWS
            or is_foreign_workflow_name(path.name)
        )
    )


def declares_pull_request(text: str) -> bool:
    return any(
        pattern.search(text) is not None
        for pattern in (
            PULL_REQUEST_BLOCK_RE,
            PULL_REQUEST_FLOW_MAP_RE,
            PULL_REQUEST_FLOW_SEQUENCE_RE,
        )
    )


def push_section(text: str) -> list[str]:
    lines = text.splitlines()
    for index, line in enumerate(lines):
        if line == "  push:":
            section = []
            for candidate in lines[index + 1 :]:
                if candidate and not candidate.startswith(" "):
                    break
                if re.match(r"^  [A-Za-z_][A-Za-z0-9_-]*:\s*$", candidate):
                    break
                section.append(candidate)
            return section
    return []


class WorkflowProjectBoundaryTests(unittest.TestCase):
    def test_foreign_filename_detection_is_case_insensitive_and_position_independent(self):
        for name in (
            "FTMO-proof.yml",
            "LightUp-check.yaml",
            "ZCLOUD-recovery.yml",
            "probe-ZCloud-dashboard.yml",
            "legacy-lightup-proof.yml",
        ):
            with self.subTest(name=name):
                self.assertTrue(is_foreign_workflow_name(name))

        for name in (
            "raise-quality.yml",
            "workflow-project-boundary.yml",
            "cloud-provider-contract.yml",
        ):
            with self.subTest(name=name):
                self.assertFalse(is_foreign_workflow_name(name))

    def test_pull_request_detection_covers_block_map_and_sequence_variants(self):
        for text in (
            "on:\n  pull_request:\n",
            "on:\n  \"pull_request\":\n",
            "on:\n  'pull_request':\n",
            "on: {pull_request: null, workflow_dispatch: null}\n",
            'on: {"pull_request": null, workflow_dispatch: null}\n',
            "'on': {'pull_request': null, workflow_dispatch: null}\n",
            '"on": {pull_request: null, workflow_dispatch: null}\n',
            "on: [push, pull_request]\n",
            "on: [\\n  push,\\n  pull_request,\\n]\\n",
            '"on": [\\n  workflow_dispatch,\\n  "pull_request",\\n]\\n',
            'on: [push, "pull_request"]\n',
            "'on': [workflow_dispatch, 'pull_request']\n",
        ):
            with self.subTest(text=text):
                self.assertTrue(declares_pull_request(text))

        self.assertFalse(declares_pull_request("on:\n  push:\n"))
        self.assertFalse(declares_pull_request("on: [push, workflow_dispatch]\n"))
        self.assertFalse(declares_pull_request("# pull_request:\non:\n  push:\n"))

    def test_no_new_foreign_project_workflows_are_added_to_raiseai(self):
        current = {path.name for path in foreign_workflows()}
        unexpected = current - LEGACY_FOREIGN_WORKFLOWS
        self.assertEqual(
            unexpected,
            set(),
            "RaiseAI must not accumulate new FTMO/LightUp/zCloud operational "
            f"workflows; add them to their owning repository instead: {sorted(unexpected)}",
        )

    def test_legacy_foreign_workflows_never_run_on_pull_requests(self):
        inspected = 0
        for path in foreign_workflows():
            inspected += 1
            text = path.read_text(encoding="utf-8")
            with self.subTest(workflow=path.name):
                self.assertFalse(
                    declares_pull_request(text),
                    f"{path.name}: legacy cross-project workflows must never allocate "
                    "work in response to RaiseAI pull requests",
                )

        self.assertGreater(
            inspected,
            0,
            "project-boundary contract must inspect the remaining legacy foreign workflows",
        )

    def test_legacy_push_triggers_are_self_scoped_to_main(self):
        for path in foreign_workflows():
            text = path.read_text(encoding="utf-8")
            section = push_section(text)
            with self.subTest(workflow=path.name):
                self.assertTrue(section, f"{path.name}: legacy workflow must keep an explicit push block")
                self.assertIn("    branches: [main]", section)
                self.assertIn("    paths:", section)
                path_entries = [line.strip() for line in section if line.lstrip().startswith("- ")]
                self.assertEqual(
                    path_entries,
                    [f'- ".github/workflows/{path.name}"'],
                    f"{path.name}: push must be scoped only to its own workflow file",
                )

    def test_nonlegacy_workflows_do_not_hide_foreign_project_markers(self):
        offenders = []
        for path in sorted(WORKFLOWS.glob("*.y*ml")):
            if path.name in LEGACY_FOREIGN_WORKFLOWS:
                continue
            text = path.read_text(encoding="utf-8")
            if FOREIGN_MARKER_RE.search(text):
                offenders.append(path.name)

        self.assertEqual(
            offenders,
            [],
            "RaiseAI workflow files outside the legacy allowlist must not embed "
            f"FTMO/LightUp/zCloud orchestration markers: {offenders}",
        )

    def test_allowlist_is_cleanup_friendly(self):
        current = {path.name for path in foreign_workflows()}
        self.assertTrue(
            current <= LEGACY_FOREIGN_WORKFLOWS,
            "removing legacy foreign workflows must remain allowed without updating this contract",
        )


if __name__ == "__main__":
    unittest.main()
