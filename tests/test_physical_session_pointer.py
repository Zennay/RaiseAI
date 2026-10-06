import importlib.util
import json
import os
import pathlib
import tempfile
import unittest
from unittest import mock


ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools" / "physical-session-pointer.py"
SPEC = importlib.util.spec_from_file_location("physical_session_pointer", SCRIPT)
pointer = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(pointer)


class PhysicalSessionPointerTests(unittest.TestCase):
    def create_session(self, root: pathlib.Path, name: str = "session-a") -> pathlib.Path:
        session = root / name
        session.mkdir()
        (session / "session.json").write_text(
            json.dumps({"schema_version": 1}) + "\n",
            encoding="utf-8",
        )
        return session

    def test_publish_and_resolve_canonical_session(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = pathlib.Path(tmp)
            evidence = base / "evidence"
            evidence.mkdir()
            session = self.create_session(evidence)
            state = base / "state"
            pointer_path = state / "latest-session"

            published = pointer.publish_latest(pointer_path, session, evidence)
            self.assertEqual(published, session.resolve())
            self.assertEqual(pointer_path.stat().st_mode & 0o777, 0o600)
            self.assertEqual(pointer.resolve_latest(pointer_path, evidence), session.resolve())
            self.assertEqual(pointer_path.read_text(encoding="utf-8"), str(session.resolve()) + "\n")

    def test_publish_replace_failure_preserves_previous_pointer(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = pathlib.Path(tmp)
            evidence = base / "evidence"
            evidence.mkdir()
            first = self.create_session(evidence, "first")
            second = self.create_session(evidence, "second")
            pointer_path = base / "latest-session"
            pointer.publish_latest(pointer_path, first, evidence)
            original = pointer_path.read_bytes()

            with mock.patch.object(pointer.os, "replace", side_effect=OSError("simulated interruption")):
                with self.assertRaisesRegex(pointer.PointerError, "atomic latest-session publish failed"):
                    pointer.publish_latest(pointer_path, second, evidence)

            self.assertEqual(pointer_path.read_bytes(), original)
            self.assertEqual(list(base.glob(".latest-session.*.tmp")), [])

    def test_rejects_symlink_pointer_for_publish_and_resolve(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = pathlib.Path(tmp)
            evidence = base / "evidence"
            evidence.mkdir()
            session = self.create_session(evidence)
            target = base / "target"
            target.write_text(str(session.resolve()) + "\n", encoding="utf-8")
            pointer_path = base / "latest-session"
            pointer_path.symlink_to(target)

            with self.assertRaisesRegex(pointer.PointerError, "refusing symlink latest-session pointer"):
                pointer.publish_latest(pointer_path, session, evidence)
            with self.assertRaisesRegex(pointer.PointerError, "refusing symlink latest-session pointer"):
                pointer.resolve_latest(pointer_path, evidence)

    def test_rejects_truncated_multiline_and_relative_pointer(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = pathlib.Path(tmp)
            evidence = base / "evidence"
            evidence.mkdir()
            self.create_session(evidence)
            pointer_path = base / "latest-session"

            for value, pattern in (
                ("", "exactly one non-empty path"),
                ("/tmp/a\n/tmp/b\n", "exactly one non-empty path"),
                ("relative/session\n", "absolute path"),
            ):
                pointer_path.write_text(value, encoding="utf-8")
                with self.assertRaisesRegex(pointer.PointerError, pattern):
                    pointer.resolve_latest(pointer_path, evidence)

    def test_rejects_pointer_outside_evidence_root_or_missing_session_metadata(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = pathlib.Path(tmp)
            evidence = base / "evidence"
            evidence.mkdir()
            outside = self.create_session(base, "outside")
            pointer_path = base / "latest-session"
            pointer_path.write_text(str(outside.resolve()) + "\n", encoding="utf-8")
            with self.assertRaisesRegex(pointer.PointerError, "escapes evidence root"):
                pointer.resolve_latest(pointer_path, evidence)

            missing = evidence / "missing-metadata"
            missing.mkdir()
            pointer_path.write_text(str(missing.resolve()) + "\n", encoding="utf-8")
            with self.assertRaisesRegex(pointer.PointerError, "cannot stat session metadata"):
                pointer.resolve_latest(pointer_path, evidence)

    def test_rejects_session_metadata_symlink(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = pathlib.Path(tmp)
            evidence = base / "evidence"
            evidence.mkdir()
            session = evidence / "session-a"
            session.mkdir()
            real = base / "real-session.json"
            real.write_text('{"schema_version":1}\n', encoding="utf-8")
            (session / "session.json").symlink_to(real)
            pointer_path = base / "latest-session"

            with self.assertRaisesRegex(pointer.PointerError, "refusing symlink session metadata"):
                pointer.publish_latest(pointer_path, session, evidence)


if __name__ == "__main__":
    unittest.main()
