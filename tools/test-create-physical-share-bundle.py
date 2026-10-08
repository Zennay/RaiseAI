#!/usr/bin/env python3
"""Regression tests for the physical evidence share boundary."""
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

SPEC = importlib.util.spec_from_file_location(
    "share_bundle", Path(__file__).with_name("create-physical-share-bundle.py"))
module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(module)


class ShareBundleTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / "evidence"
        self.source.mkdir()
        self.dest = self.root / "share"
        self.docs = {
            "e2e-result.json": {"schema_version": 2, "valid": True},
            "v1-result.json": {"schema_version": 1, "v1_gate_passed": True},
            "quality-result.json": {
                "schema_version": 1, "valid": True,
                "quality_evidence_complete": True},
        }
        self.write_all()

    def write_all(self):
        for name, document in self.docs.items():
            (self.source / name).write_text(json.dumps(document), encoding="utf-8")

    def test_valid_bundle_contains_only_canonical_files(self):
        (self.source / "session.json").write_text('{"watch_serial":"private"}')
        module.bundle(self.source, self.dest)
        self.assertEqual(set(p.name for p in self.dest.iterdir()), set(module.NAMES))
        self.assertFalse((self.dest / "session.json").exists())

    def test_missing_input_fails_without_destination(self):
        (self.source / "v1-result.json").unlink()
        with self.assertRaises(OSError):
            module.bundle(self.source, self.dest)
        self.assertFalse(self.dest.exists())

    def test_symlink_input_rejected(self):
        path = self.source / "v1-result.json"
        path.unlink()
        path.symlink_to(self.source / "quality-result.json")
        with self.assertRaises(OSError):
            module.bundle(self.source, self.dest)
        self.assertFalse(self.dest.exists())

    def test_duplicate_keys_rejected(self):
        (self.source / "v1-result.json").write_text(
            '{"schema_version":1,"v1_gate_passed":true,"v1_gate_passed":true}')
        with self.assertRaises(ValueError):
            module.bundle(self.source, self.dest)
        self.assertFalse(self.dest.exists())

    def test_sensitive_nested_field_rejected(self):
        self.docs["quality-result.json"]["metadata"] = [
            {"payload": {"watch_serial": "private"}}]
        self.write_all()
        with self.assertRaises(ValueError):
            module.bundle(self.source, self.dest)
        self.assertFalse(self.dest.exists())

    def test_false_gate_rejected(self):
        self.docs["v1-result.json"]["v1_gate_passed"] = False
        self.write_all()
        with self.assertRaises(ValueError):
            module.bundle(self.source, self.dest)

    def test_existing_destination_never_overwritten(self):
        self.dest.mkdir()
        sentinel = self.dest / "untouched"
        sentinel.write_text("keep")
        with self.assertRaises(FileExistsError):
            module.bundle(self.source, self.dest)
        self.assertEqual(sentinel.read_text(), "keep")

    def test_oversized_json_rejected(self):
        (self.source / "e2e-result.json").write_text(" " * (module.LIMIT + 1))
        with self.assertRaises(ValueError):
            module.bundle(self.source, self.dest)

    def test_invalid_json_rejected(self):
        (self.source / "e2e-result.json").write_text("{bad")
        with self.assertRaises(json.JSONDecodeError):
            module.bundle(self.source, self.dest)


if __name__ == "__main__":
    unittest.main()
