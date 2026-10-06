import importlib.util
import os
import pathlib
import tempfile
import unittest
from unittest import mock


ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools" / "publish-physical-result.py"
SPEC = importlib.util.spec_from_file_location("publish_physical_result", SCRIPT)
publisher = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(publisher)


class PhysicalResultPublisherTests(unittest.TestCase):
    def test_publishes_complete_json_exclusively(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            source = root / "source.json"
            destination = root / "e2e-result.json"
            payload = b'{"valid":true,"route":"quick_ai"}\n'
            source.write_bytes(payload)

            publisher.publish_result(source, destination)

            self.assertEqual(destination.read_bytes(), payload)
            self.assertEqual(destination.stat().st_mode & 0o777, 0o600)
            self.assertEqual(list(root.glob(".e2e-result.json.*.tmp")), [])

    def test_existing_result_is_never_overwritten(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            source = root / "source.json"
            destination = root / "v1-result.json"
            source.write_text('{"v1_gate_passed":true}\n', encoding="utf-8")
            destination.write_text('{"original":true}\n', encoding="utf-8")
            original = destination.read_bytes()

            with self.assertRaisesRegex(publisher.ResultPublishError, "refusing to overwrite"):
                publisher.publish_result(source, destination)

            self.assertEqual(destination.read_bytes(), original)

    def test_dangling_destination_symlink_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            source = root / "source.json"
            source.write_text('{"valid":true}\n', encoding="utf-8")
            destination = root / "result.json"
            target = root / "unexpected-target"
            destination.symlink_to(target)

            with self.assertRaisesRegex(publisher.ResultPublishError, "refusing symlink result destination"):
                publisher.publish_result(source, destination)

            self.assertFalse(target.exists())

    def test_invalid_or_non_object_json_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            destination = root / "result.json"
            for content, pattern in (
                ("", "empty"),
                ("not-json", "valid UTF-8 JSON"),
                ("[]\n", "root must be an object"),
            ):
                source = root / "source.json"
                source.write_text(content, encoding="utf-8")
                with self.assertRaisesRegex(publisher.ResultPublishError, pattern):
                    publisher.publish_result(source, destination)
                self.assertFalse(destination.exists())

    def test_link_failure_does_not_leave_partial_destination(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            source = root / "source.json"
            destination = root / "result.json"
            source.write_text('{"valid":true}\n', encoding="utf-8")

            with mock.patch.object(publisher.os, "link", side_effect=OSError("simulated publish failure")):
                with self.assertRaisesRegex(publisher.ResultPublishError, "exclusive result publish failed"):
                    publisher.publish_result(source, destination)

            self.assertFalse(destination.exists())
            self.assertEqual(list(root.glob(".result.json.*.tmp")), [])


if __name__ == "__main__":
    unittest.main()
