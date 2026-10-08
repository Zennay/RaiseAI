"""Regression checks for the physical sharing boundary (issue #514)."""
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools" / "create-physical-share-bundle.py"
spec = importlib.util.spec_from_file_location("physical_share_bundle", SCRIPT)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


class PhysicalShareBundleTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.source = self.base / "session"
        self.source.mkdir()
        self.dest = self.base / "share"
        self.payloads = {
            "e2e-result.json": {"valid": True, "outcome": "success", "route": "quick_ai", "answer_present": True},
            "v1-result.json": {"schema_version": 1, "v1_gate_passed": True},
            "quality-result.json": {"schema_version": 1, "valid": True,
                                    "quality_evidence_complete": True},
        }
        for name, payload in self.payloads.items():
            (self.source / name).write_text(json.dumps(payload), encoding="utf-8")

    def test_allowlist_only(self):
        (self.source / "session.json").write_text('{"watch_serial":"secret"}')
        mod.bundle(self.source, self.dest)
        self.assertEqual(set(x.name for x in self.dest.iterdir()), set(mod.FILES))

    def test_missing_file(self):
        (self.source / "v1-result.json").unlink()
        with self.assertRaises(OSError):
            mod.bundle(self.source, self.dest)
        self.assertFalse(self.dest.exists())

    def test_symlink(self):
        file = self.source / "e2e-result.json"
        file.rename(self.source / "real.json")
        file.symlink_to("real.json")
        with self.assertRaises(OSError):
            mod.bundle(self.source, self.dest)
        self.assertFalse(self.dest.exists())

    def test_duplicate_json_keys(self):
        (self.source / "e2e-result.json").write_text('{"outcome":"success","route":"quick_ai","answer_present":true,"valid":true,"valid":true}')
        with self.assertRaises(mod.ShareError):
            mod.bundle(self.source, self.dest)
        self.assertFalse(self.dest.exists())

    def test_sensitive_recursive(self):
        payload = self.payloads["e2e-result.json"]
        payload["metadata"] = [{"answer_text": "private"}]
        (self.source / "e2e-result.json").write_text(json.dumps(payload))
        with self.assertRaises(mod.ShareError):
            mod.bundle(self.source, self.dest)

    def test_failed_gate(self):
        payload = self.payloads["v1-result.json"]
        payload["v1_gate_passed"] = False
        (self.source / "v1-result.json").write_text(json.dumps(payload))
        with self.assertRaises(mod.ShareError):
            mod.bundle(self.source, self.dest)

    def test_existing_destination_preserved(self):
        self.dest.mkdir()
        marker = self.dest / "keep"
        marker.write_text("unchanged")
        with self.assertRaises(mod.ShareError):
            mod.bundle(self.source, self.dest)
        self.assertEqual(marker.read_text(), "unchanged")

    def test_oversized_document(self):
        file = self.source / "quality-result.json"
        file.write_text(" " * (mod.MAX_BYTES + 1))
        with self.assertRaises(mod.ShareError):
            mod.bundle(self.source, self.dest)

    def test_invalid_json(self):
        (self.source / "quality-result.json").write_text("{")
        with self.assertRaises(mod.ShareError):
            mod.bundle(self.source, self.dest)


if __name__ == "__main__":
    unittest.main()
