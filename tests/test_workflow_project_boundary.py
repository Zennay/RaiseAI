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

FOREIGN_PREFIXES = (
    "ftmo-",
    "lightup-",
    "zcloud-",
    "cancel-stale-zcloud-",
)

FOREIGN_MARKER_RE = re.compile(r"(?i)\b(?:ftmo|lightup|zcloud)\b")


def foreign_workflows() -> list[Path]:
    return sorted(
        path
        for path in WORKFLOWS.iterdir()
        if path.is_file()
        and path.suffix in {".yml", ".yaml"}
        and path.name.startswith(FOREIGN_PREFIXES)
    )


def declares_pull_request(text: str) -> bool:
    return re.search(r"(?m)^\s{0,2}pull_request\s*:", text) is not None


class WorkflowProjectBoundaryTests(unittest.TestCase):
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
