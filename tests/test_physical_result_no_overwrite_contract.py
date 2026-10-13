"""Fail-closed physical observation result publication contracts.

Run with: python -m unittest tests.test_physical_result_no_overwrite_contract
These are offline filesystem fixtures; no watch or VPS is involved.
"""
import importlib.util
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools" / "validate-physical-observations.py"
SPEC = importlib.util.spec_from_file_location("physical_observation_publication", SCRIPT)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("physical observations validator cannot be loaded")
validator = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(validator)

PAYLOAD = {"valid": True, "quality_evidence_complete": True}


class PhysicalResultNoOverwriteContracts(unittest.TestCase):
    def test_fresh_result_published_and_temp_files_removed(self):
        with tempfile.TemporaryDirectory() as directory:
            parent = Path(directory)
            output = parent / "result.json"
            validator.write_new_json_atomically(output, PAYLOAD)
            self.assertTrue(output.is_file())
            self.assertIn('"quality_evidence_complete": true', output.read_text())
            self.assertEqual(sorted(p.name for p in parent.iterdir()), ["result.json"])

    def test_existing_result_never_overwritten(self):
        with tempfile.TemporaryDirectory() as directory:
            parent = Path(directory)
            output = parent / "result.json"
            output.write_bytes(b"trusted-original\n")
            with self.assertRaisesRegex(validator.ObservationError, "refusing to overwrite"):
                validator.write_new_json_atomically(output, PAYLOAD)
            self.assertEqual(output.read_bytes(), b"trusted-original\n")
            self.assertEqual(sorted(p.name for p in parent.iterdir()), ["result.json"])

    def test_symlink_output_never_replaces_target(self):
        with tempfile.TemporaryDirectory() as directory:
            parent = Path(directory)
            target = parent / "target.json"
            target.write_bytes(b"protected\n")
            output = parent / "result.json"
            output.symlink_to(target)
            with self.assertRaisesRegex(validator.ObservationError, "refusing to overwrite"):
                validator.write_new_json_atomically(output, PAYLOAD)
            self.assertTrue(output.is_symlink())
            self.assertEqual(target.read_bytes(), b"protected\n")
            self.assertEqual(sorted(p.name for p in parent.iterdir()), ["result.json", "target.json"])

    def test_symlink_parent_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            parent = Path(directory)
            real = parent / "real"
            real.mkdir()
            alias = parent / "alias"
            alias.symlink_to(real, target_is_directory=True)
            with self.assertRaises(OSError):
                validator.write_new_json_atomically(alias / "result.json", PAYLOAD)
            self.assertEqual(list(real.iterdir()), [])


if __name__ == "__main__":
    unittest.main()
