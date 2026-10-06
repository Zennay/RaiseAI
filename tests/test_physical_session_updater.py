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
    def write_session(self, root: pathlib.Path) -> pathlib.Path:
        path = root / "session.json"
        path.write_text(json.dumps(session_payload()) + "\n", encoding="utf-8")
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

    def test_updates_allowed_field_atomically_and_preserves_mode(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            path = self.write_session(root)
            updater.update_session(path, "e2e_passed", "true")
            payload = json.loads(path.read_text(encoding="utf-8"))
            self.assertTrue(payload["e2e_passed"])
            self.assertEqual(path.stat().st_mode & 0o777, 0o640)
            self.assertEqual(list(root.glob(".session.json.*.tmp")), [])

    def test_replace_failure_preserves_original_and_cleans_temp(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            path = self.write_session(root)
            original = path.read_bytes()
            with mock.patch.object(updater.os, "replace", side_effect=OSError("simulated interruption")):
                with self.assertRaisesRegex(updater.SessionUpdateError, "atomic session update failed"):
                    updater.update_session(path, "e2e_passed", "true")
            self.assertEqual(path.read_bytes(), original)
            self.assertEqual(list(root.glob(".session.json.*.tmp")), [])

    def test_rejects_symlink_session_metadata_for_read_and_write(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            target = self.write_session(root)
            link = root / "session-link.json"
            link.symlink_to(target)
            with self.assertRaisesRegex(updater.SessionUpdateError, "refusing symlink"):
                updater.read_session_field(link, "app_version")
            with self.assertRaisesRegex(updater.SessionUpdateError, "refusing symlink"):
                updater.update_session(link, "e2e_passed", "true")

    def test_rejects_duplicate_json_keys_for_read_and_write(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            path = root / "session.json"
            path.write_text(
                '{"schema_version":1,"app_version":"1.5.2","e2e_passed":false,"e2e_passed":true}\n',
                encoding="utf-8",
            )
            with self.assertRaisesRegex(updater.SessionUpdateError, "duplicate JSON object key"):
                updater.read_session_field(path, "app_version")
            with self.assertRaisesRegex(updater.SessionUpdateError, "duplicate JSON object key"):
                updater.update_session(path, "e2e_passed", "true")

    def test_rejects_invalid_read_types_and_multiline_values(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            payload = session_payload()
            payload["e2e_passed"] = 1
            path = root / "session.json"
            path.write_text(json.dumps(payload) + "\n", encoding="utf-8")
            with self.assertRaisesRegex(updater.SessionUpdateError, "e2e_passed must be boolean"):
                updater.read_session_field(path, "e2e_passed")

            payload = session_payload()
            payload["watch_serial"] = "watch-1\nother"
            path.write_text(json.dumps(payload) + "\n", encoding="utf-8")
            with self.assertRaisesRegex(updater.SessionUpdateError, "single-line"):
                updater.read_session_field(path, "watch_serial")

    def test_rejects_unknown_or_invalid_mutation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            path = self.write_session(root)
            with self.assertRaisesRegex(updater.SessionUpdateError, "field is not mutable"):
                updater.update_session(path, "watch_serial", "other")
            with self.assertRaisesRegex(updater.SessionUpdateError, "must be true or false"):
                updater.update_session(path, "e2e_passed", "yes")


if __name__ == "__main__":
    unittest.main()
