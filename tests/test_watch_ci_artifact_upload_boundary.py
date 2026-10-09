"""Fail-closed checks on the Watch CI artifact publication boundaries.

The preserved v1.5.2 physical handoff is immutable. This source-only test
protects *new CI outputs* from accidentally publishing an entire checkout,
operator evidence, or secret-bearing runner directories.
"""

from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "watch-app-test.yml"
UPLOAD_ACTION = "actions/upload-artifact@043fb46d1a93c77aae656e7c1c64a875d1fc6a0a"


def _upload_steps(workflow: str) -> dict[str, str]:
    """Extract fixed-indentation Watch CI steps; reject shadowed step names."""
    starts = list(re.finditer(r"(?m)^      - name: ([^\r\n]+)\n", workflow))
    if not starts:
        raise ValueError("no named Watch CI steps")
    result = {}
    for index, start in enumerate(starts):
        name = start.group(1)
        if name in result:
            raise ValueError("duplicate Watch CI step name")
        stop = starts[index + 1].start() if index + 1 < len(starts) else len(workflow)
        result[name] = workflow[start.start():stop]
    return result


def verify_upload_boundary(workflow: str) -> None:
    steps = _upload_steps(workflow)
    expected = {
        "Upload exact main physical handoff": {
            "if": "github.event_name == 'push' && github.ref == 'refs/heads/main'",
            "name": "RaiseAI-Watch7-v${{ env.RAISE_HANDOFF_VERSION }}-physical-handoff-${{ github.run_id }}",
            "path": "${{ env.RAISE_HANDOFF_DIR }}",
        },
        "Upload debug Watch APK": {
            "if": None,
            "name": "RaiseAI-Watch7-v${{ env.RAISE_HANDOFF_VERSION }}-${{ github.run_id }}",
            "path": "app/build/outputs/apk/debug/app-debug.apk",
        },
    }
    upload_uses = re.findall(
        r"(?m)^        uses: (actions/upload-artifact@[^\s#]+)",
        workflow,
    )
    if upload_uses != [UPLOAD_ACTION, UPLOAD_ACTION]:
        raise ValueError("unexpected artifact upload action or extra upload step")
    actual_uploads = {
        name for name, body in steps.items()
        if "uses: actions/upload-artifact@" in body
    }
    if actual_uploads != set(expected):
        raise ValueError("unexpected Watch artifact upload step")

    for name, boundary in expected.items():
        step = steps[name]
        lines = step.splitlines()
        main_fields = [
            match.groups()
            for line in lines
            if (match := re.fullmatch(r"        (if|uses|with):(?: (.*))?", line))
        ]
        expected_main = [("uses", UPLOAD_ACTION + " # v7.0.1 (node24)"), ("with", None)]
        if boundary["if"] is not None:
            expected_main.insert(0, ("if", boundary["if"]))
        if main_fields != expected_main:
            raise ValueError(f"{name}: upload action, condition or step shape changed")

        if "        with:" not in lines:
            raise ValueError(f"{name}: missing artifact options")
        options = []
        for line in lines[lines.index("        with:") + 1:]:
            if not line.strip():
                continue
            match = re.fullmatch(r"          ([a-z-]+): (.+)", line)
            if match is None:
                raise ValueError(f"{name}: unreviewed artifact option or indentation")
            options.append(match.groups())
        expected_options = [
            ("name", boundary["name"]),
            ("path", boundary["path"]),
            ("if-no-files-found", "error"),
            ("retention-days", "14"),
        ]
        if options != expected_options:
            raise ValueError(f"{name}: artifact publish path/options drifted")

    # The handoff path must be generated under RUNNER_TEMP, not populated
    # from the checked-out repository or a caller-controlled environment.
    if workflow.count('          handoff_dir="$RUNNER_TEMP/raiseai-physical-handoff"') != 1:
        raise ValueError("physical handoff output no longer bound to RUNNER_TEMP")
    if workflow.count('          echo "RAISE_HANDOFF_DIR=$handoff_dir" >> "$GITHUB_ENV"') != 1:
        raise ValueError("physical handoff output identity no longer exported")
    if workflow.index("      - name: Build and verify physical handoff") >= workflow.index(
        "      - name: Upload exact main physical handoff"
    ):
        raise ValueError("handoff verification must precede publication")


class WatchCiArtifactUploadBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.workflow = WORKFLOW.read_text(encoding="utf-8")

    def test_repository_ci_has_narrow_upload_paths(self):
        verify_upload_boundary(self.workflow)

    def test_rejects_checkout_root_as_artifact(self):
        mutated = self.workflow.replace(
            "          path: app/build/outputs/apk/debug/app-debug.apk",
            "          path: .",
            1,
        )
        self.assertNotEqual(mutated, self.workflow)
        with self.assertRaisesRegex(ValueError, "artifact publish path/options drifted"):
            verify_upload_boundary(mutated)

    def test_rejects_unconditional_physical_handoff_upload(self):
        mutated = self.workflow.replace(
            "        if: github.event_name == 'push' && github.ref == 'refs/heads/main'\n",
            "",
            1,
        )
        self.assertNotEqual(mutated, self.workflow)
        with self.assertRaisesRegex(ValueError, "condition or step shape"):
            verify_upload_boundary(mutated)

    def test_rejects_unreviewed_artifact_retention(self):
        mutated = self.workflow.replace("          retention-days: 14", "          retention-days: 90", 1)
        self.assertNotEqual(mutated, self.workflow)
        with self.assertRaisesRegex(ValueError, "artifact publish path/options drifted"):
            verify_upload_boundary(mutated)

    def test_rejects_shadowed_artifact_path(self):
        mutated = self.workflow.replace(
            "          path: app/build/outputs/apk/debug/app-debug.apk",
            "          path: app/build/outputs/apk/debug/app-debug.apk\n          path: .",
            1,
        )
        self.assertNotEqual(mutated, self.workflow)
        with self.assertRaisesRegex(ValueError, "artifact publish path/options drifted"):
            verify_upload_boundary(mutated)

    def test_rejects_extra_upload_action(self):
        mutated = self.workflow + (
            "\n      - name: Upload whole workspace\n"
            "        uses: " + UPLOAD_ACTION + " # v7.0.1 (node24)\n"
            "        with:\n"
            "          name: all-files\n"
            "          path: .\n"
        )
        with self.assertRaisesRegex(ValueError, "extra upload step"):
            verify_upload_boundary(mutated)

    def test_rejects_handoff_outside_runner_temp(self):
        mutated = self.workflow.replace(
            '          handoff_dir="$RUNNER_TEMP/raiseai-physical-handoff"',
            '          handoff_dir="$GITHUB_WORKSPACE"',
            1,
        )
        self.assertNotEqual(mutated, self.workflow)
        with self.assertRaisesRegex(ValueError, "RUNNER_TEMP"):
            verify_upload_boundary(mutated)


if __name__ == "__main__":
    unittest.main()
