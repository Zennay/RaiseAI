from pathlib import Path
import re
import stat
import tempfile
import unittest

try:
    from tests.test_workflow_privilege_boundary import workflow_security_metadata
except ModuleNotFoundError as exc:
    if exc.name != "tests":
        raise
    from test_workflow_privilege_boundary import workflow_security_metadata


ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"
BOUNDARY_WORKFLOW = WORKFLOWS / "workflow-project-boundary.yml"

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


PULL_REQUEST_EVENTS = {"pull_request", "pull_request_target"}


def read_workflow_text(path: Path) -> str:
    mode = path.lstat().st_mode
    if stat.S_ISLNK(mode):
        raise ValueError(f"{path.name}: workflow input must not be a symbolic link")
    if not stat.S_ISREG(mode):
        raise ValueError(f"{path.name}: workflow input must be a regular file")
    try:
        return path.read_bytes().decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise ValueError(f"{path.name}: workflow input must be valid UTF-8") from exc


def pull_request_events(path: Path) -> set[str]:
    events = set(workflow_security_metadata(path)["events"])
    return events & PULL_REQUEST_EVENTS


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

    def test_pull_request_detection_covers_block_scalar_sequence_flow_and_quotes(self):
        positives = (
            "on:\n  pull_request:\n",
            "on:\n  pull_request_target:\n",
            "on:\n  \"pull_request\":\n",
            "on:\n  'pull_request':\n",
            "on: {pull_request: null, workflow_dispatch: null}\n",
            'on: {"pull_request": null, workflow_dispatch: null}\n',
            "'on': {'pull_request': null, workflow_dispatch: null}\n",
            '"on": {pull_request: null, workflow_dispatch: null}\n',
            "on: {\n    push: {paths: ['src/**']},\n    pull_request: null\n}\n",
            "'on': {\n    workflow_dispatch: null,\n    'pull_request_target': null\n}\n",
            "on: pull_request\n",
            "on: pull_request_target\n",
            '"on": "pull_request"\n',
            "'on': 'pull_request' # legacy scalar trigger\n",
            "on: [push, pull_request]\n",
            "on: [push, pull_request_target]\n",
            "on: [\n  push,\n  pull_request,\n]\n",
            "on: [\n  push,\n  pull_request # guarded legacy trigger\n]\n",
            '"on": [\n  workflow_dispatch,\n  "pull_request",\n]\n',
            'on: [push, "pull_request"]\n',
            "'on': [workflow_dispatch, 'pull_request']\n",
        )
        negatives = (
            "on:\n  push:\n",
            "on: [push, workflow_dispatch]\n",
            "# pull_request:\non:\n  push:\n",
            "on: {push: {paths: ['pull_request/**']}, workflow_dispatch: null}\n",
        )

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for index, text in enumerate(positives):
                path = root / f"positive-{index}.yml"
                path.write_text(text, encoding="utf-8")
                with self.subTest(text=text):
                    self.assertTrue(pull_request_events(path))

            for index, text in enumerate(negatives):
                path = root / f"negative-{index}.yml"
                path.write_text(text, encoding="utf-8")
                with self.subTest(text=text):
                    self.assertEqual(pull_request_events(path), set())


    def test_semantic_trigger_detection_fails_closed_on_invalid_on_surface(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "invalid-on.yml"
            path.write_text("on:\n  - {pull_request: {}}\n", encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "workflow security"):
                pull_request_events(path)

    def test_boundary_workflow_pins_semantic_parser_runtime(self):
        workflow = read_workflow_text(BOUNDARY_WORKFLOW)
        self.assertIn("Verify Ruby/Psych runtime", workflow)
        self.assertIn('expected = ["3.2.3", "5.0.1"]', workflow)
        self.assertIn('ruby --disable-gems -e \'require "psych";', workflow)
        self.assertIn(
            "python3 -m unittest tests.test_workflow_project_boundary",
            workflow,
        )

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
            with self.subTest(workflow=path.name):
                self.assertEqual(
                    pull_request_events(path),
                    set(),
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
            text = read_workflow_text(path)
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
            text = read_workflow_text(path)
            if FOREIGN_MARKER_RE.search(text):
                offenders.append(path.name)

        self.assertEqual(
            offenders,
            [],
            "RaiseAI workflow files outside the legacy allowlist must not embed "
            f"FTMO/LightUp/zCloud orchestration markers: {offenders}",
        )

    def test_workflow_text_reader_rejects_symlink_nonregular_and_invalid_utf8(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            regular = root / "regular.yml"
            regular.write_text("on: [push]\n", encoding="utf-8")
            symlink = root / "linked.yml"
            symlink.symlink_to(regular)
            with self.assertRaisesRegex(ValueError, "must not be a symbolic link"):
                read_workflow_text(symlink)

            directory = root / "directory.yml"
            directory.mkdir()
            with self.assertRaisesRegex(ValueError, "must be a regular file"):
                read_workflow_text(directory)

            invalid = root / "invalid.yml"
            invalid.write_bytes(b"on: [push]\xff")
            with self.assertRaisesRegex(ValueError, "must be valid UTF-8"):
                read_workflow_text(invalid)

    def test_allowlist_is_cleanup_friendly(self):
        current = {path.name for path in foreign_workflows()}
        self.assertTrue(
            current <= LEGACY_FOREIGN_WORKFLOWS,
            "removing legacy foreign workflows must remain allowed without updating this contract",
        )


if __name__ == "__main__":
    unittest.main()
