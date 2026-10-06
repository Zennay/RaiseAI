import importlib.util
import json
import os
import pathlib
import tempfile
import unittest
from unittest import mock


ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools" / "update-physical-session.py"
SPEC = importlib.util.spec_from_file_location("update_physical_session", SCRIPT)
updater = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(updater)


def session_payload():
    return {
        "schema_version": 1,
        "started_at_utc": "2026-10-06T09:00:00Z",
        "app_version": "1.5.2",
        "source_revision": "a" * 40,
        "watch_model": "SM_L315F",
        "watch_serial": "watch-1",
        "install_mode": "prebuilt_apk",
        "apk_sha256": "b" * 64,
        "installed_apk_sha256": "b" * 64,
        "e2e_passed": False,
        "v1_gate_passed": False,
    }


class PhysicalSessionUpdaterTests(unittest.TestCase):
    def write_session(self, root: pathlib.Path, payload=None) -> pathlib.Path:
        path = root / "session.json"
        path.write_text(
            json.dumps(payload or session_payload()) + "\n",
            encoding="utf-8",
        )
        os.chmod(path, 0o640)
        return path

    def test_reads_only_allowed_typed_fields(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            path = self.write_session(root)
            self.assertEqual(updater.read_session_field(path, "app_version"), "1.5.2")
            self.assertEqual(updater.read_session_field(path, "watch_serial"), "watch-1")
            self.assertEqual(updater.read_session_field(path, "e2e_passed"), "false")
            with self.assertRaisesRegex(updater.SessionUpdateError, "field is not readable"):
                updater.read_session_field(path, "apk_sha256")

    def test_e2e_gate_commits_flag_and_timestamp_in_one_atomic_write(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            path = self.write_session(root)
            updater.mark_gate_passed(path, "e2e", "2026-10-06T09:05:00Z")
            payload = json.loads(path.read_text(encoding="utf-8"))
            self.assertTrue(payload["e2e_passed"])
            self.assertEqual(payload["e2e_verified_at_utc"], "2026-10-06T09:05:00Z")
            self.assertEqual(path.stat().st_mode & 0o777, 0o640)
            self.assertEqual(list(root.glob(".session.json.*.tmp")), [])

    def test_replace_failure_preserves_complete_original_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            path = self.write_session(root)
            original = path.read_bytes()
            with mock.patch.object(updater.os, "replace", side_effect=OSError("simulated interruption")):
                with self.assertRaisesRegex(updater.SessionUpdateError, "atomic session update failed"):
                    updater.mark_gate_passed(path, "e2e", "2026-10-06T09:05:00Z")
            self.assertEqual(path.read_bytes(), original)
            self.assertEqual(list(root.glob(".session.json.*.tmp")), [])

    def test_v1_requires_committed_e2e_and_monotonic_timestamp(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            path = self.write_session(root)
            with self.assertRaisesRegex(updater.SessionUpdateError, "before the E2E gate"):
                updater.mark_gate_passed(path, "v1", "2026-10-06T09:10:00Z")

            updater.mark_gate_passed(path, "e2e", "2026-10-06T09:05:00Z")
            with self.assertRaisesRegex(updater.SessionUpdateError, "cannot precede E2E verification"):
                updater.mark_gate_passed(path, "v1", "2026-10-06T09:04:59Z")

            updater.mark_gate_passed(path, "v1", "2026-10-06T09:10:00Z")
            payload = json.loads(path.read_text(encoding="utf-8"))
            self.assertTrue(payload["v1_gate_passed"])
            self.assertEqual(payload["v1_verified_at_utc"], "2026-10-06T09:10:00Z")

    def test_rejects_pre_session_noncanonical_and_duplicate_gate_commits(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            path = self.write_session(root)
            with self.assertRaisesRegex(updater.SessionUpdateError, "cannot precede started_at_utc"):
                updater.mark_gate_passed(path, "e2e", "2026-10-06T08:59:59Z")
            with self.assertRaisesRegex(updater.SessionUpdateError, "canonical UTC form"):
                updater.mark_gate_passed(path, "e2e", "2026-10-06T09:05:00+00:00")

            updater.mark_gate_passed(path, "e2e", "2026-10-06T09:05:00Z")
            with self.assertRaisesRegex(updater.SessionUpdateError, "already committed"):
                updater.mark_gate_passed(path, "e2e", "2026-10-06T09:06:00Z")

    def test_rejects_symlink_session_metadata_for_read_and_gate_commit(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            target = self.write_session(root)
            link = root / "session-link.json"
            link.symlink_to(target)
            with self.assertRaisesRegex(updater.SessionUpdateError, "refusing symlink"):
                updater.read_session_field(link, "app_version")
            with self.assertRaisesRegex(updater.SessionUpdateError, "refusing symlink"):
                updater.mark_gate_passed(link, "e2e", "2026-10-06T09:05:00Z")

    def test_rejects_duplicate_json_keys_for_read_and_gate_commit(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            path = root / "session.json"
            path.write_text(
                '{"schema_version":1,"started_at_utc":"2026-10-06T09:00:00Z",'
                '"e2e_passed":false,"e2e_passed":true,"v1_gate_passed":false}\n',
                encoding="utf-8",
            )
            with self.assertRaisesRegex(updater.SessionUpdateError, "duplicate JSON object key"):
                updater.read_session_field(path, "e2e_passed")
            with self.assertRaisesRegex(updater.SessionUpdateError, "duplicate JSON object key"):
                updater.mark_gate_passed(path, "e2e", "2026-10-06T09:05:00Z")

    def test_rejects_invalid_read_types_and_multiline_values(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            payload = session_payload()
            payload["e2e_passed"] = 1
            path = self.write_session(root, payload)
            with self.assertRaisesRegex(updater.SessionUpdateError, "e2e_passed must be boolean"):
                updater.read_session_field(path, "e2e_passed")

            payload = session_payload()
            payload["watch_serial"] = "watch-1\nother"
            path.write_text(json.dumps(payload) + "\n", encoding="utf-8")
            with self.assertRaisesRegex(updater.SessionUpdateError, "single-line"):
                updater.read_session_field(path, "watch_serial")

    def test_rejects_unknown_gate_and_invalid_session_gate_types(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            path = self.write_session(root)
            with self.assertRaisesRegex(updater.SessionUpdateError, "unknown physical validation gate"):
                updater.mark_gate_passed(path, "other", "2026-10-06T09:05:00Z")

            payload = session_payload()
            payload["v1_gate_passed"] = 0
            path.write_text(json.dumps(payload) + "\n", encoding="utf-8")
            with self.assertRaisesRegex(updater.SessionUpdateError, "v1_gate_passed must be boolean"):
                updater.mark_gate_passed(path, "e2e", "2026-10-06T09:05:00Z")


if __name__ == "__main__":
    unittest.main()
