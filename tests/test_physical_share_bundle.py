"""Regression tests for the fail-closed physical sharing boundary."""
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

MODULE_PATH = Path(__file__).resolve().parents[1] / "tools" / "create-physical-share-bundle.py"
SPEC = importlib.util.spec_from_file_location("physical_share", MODULE_PATH)
share = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(share)


def examples():
    rev = "a" * 40
    return {
        "e2e-result.json": {
            "valid": True, "outcome": "success", "route": "quick_ai",
            "answer_present": True, "app_version": "1.5.2",
            "source_revision": rev,
        },
        "v1-result.json": {
            "schema_version": 1, "v1_gate_passed": True,
            "evidence_identity": {"app_version": "1.5.2", "source_revision": rev},
        },
        "quality-result.json": {
            "schema_version": 1, "valid": True, "quality_evidence_complete": True,
            "app_version": "1.5.2", "source_revision": rev,
            "apk_sha256": "b" * 64, "screen_off_tested": True,
            "background_tested": True, "ux_failures_reviewed": True,
        },
    }


class PhysicalShareTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.session = self.root / "session"
        self.session.mkdir()
        self.target = self.root / "share"
        self.data = examples()
        self.write()

    def write(self):
        for name, payload in self.data.items():
            (self.session / name).write_text(json.dumps(payload), encoding="utf-8")

    def rejects(self):
        with self.assertRaises((ValueError, OSError, UnicodeError)):
            share.make_bundle(self.session, self.target)
        self.assertFalse(self.target.exists())

    def test_valid_share_has_exactly_three_files(self):
        (self.session / "session.json").write_text('{"watch_serial":"secret"}')
        share.make_bundle(self.session, self.target)
        self.assertEqual(set(x.name for x in self.target.iterdir()), set(share.FILES))
        for name in share.FILES:
            self.assertEqual((self.target / name).read_bytes(),
                             (self.session / name).read_bytes())

    def test_missing_file(self):
        (self.session / "quality-result.json").unlink()
        self.rejects()

    def test_symlink_input(self):
        original = self.session / "v1-result.json"
        original.rename(self.root / "external.json")
        original.symlink_to(self.root / "external.json")
        self.rejects()

    def test_duplicate_key(self):
        (self.session / "e2e-result.json").write_text('{"valid":true,"valid":true}')
        self.rejects()

    def test_invalid_json(self):
        (self.session / "e2e-result.json").write_text("{broken")
        self.rejects()

    def test_oversize(self):
        (self.session / "v1-result.json").write_text(" " * (share.MAX_BYTES + 1))
        self.rejects()

    def test_recursive_sensitive_field(self):
        self.data["v1-result.json"]["extra"] = [{"nested": {"access_token": "redacted"}}]
        self.write()
        self.rejects()

    def test_failed_summary(self):
        self.data["v1-result.json"]["v1_gate_passed"] = False
        self.write()
        self.rejects()

    def test_cross_summary_identity_mismatch(self):
        self.data["quality-result.json"]["source_revision"] = "c" * 40
        self.write()
        self.rejects()

    def test_existing_output_not_overwritten(self):
        self.target.mkdir()
        (self.target / "preserve").write_text("untouched")
        with self.assertRaises(FileExistsError):
            share.make_bundle(self.session, self.target)
        self.assertEqual((self.target / "preserve").read_text(), "untouched")


if __name__ == "__main__":
    unittest.main()
