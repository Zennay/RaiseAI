"""Exercise the real tracked-JSON byte guard from discovered tests/ suite."""
import importlib.util
from pathlib import Path
import tempfile
import unittest

SOURCE = Path(__file__).resolve().parents[1] / "tools" / "test_tracked_json_source_integrity.py"
SPEC = importlib.util.spec_from_file_location("raise_json_source_integrity", SOURCE)
assert SPEC and SPEC.loader
GUARD = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(GUARD)


class TrackedJsonByteGuardDiscoveryTests(unittest.TestCase):
    def test_rejects_actual_bom_and_nul_bytes(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "contract.json"
            for raw in (b"\xef\xbb\xbf{}", b'{"name":"bad\x00value"}'):
                with self.subTest(raw=raw):
                    path.write_bytes(raw)
                    with self.assertRaisesRegex(ValueError, "forbidden bytes"):
                        GUARD.validate_json_source(path)

    def test_accepts_regular_utf8_source_and_rejects_bad_utf8(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "contract.json"
            path.write_bytes('{"name":"caf\\u00e9"}\\n'.encode("utf-8"))
            GUARD.validate_json_source(path)
            path.write_bytes(b'{"bad":"\xff"}')
            with self.assertRaises(UnicodeDecodeError):
                GUARD.validate_json_source(path)

    def test_rejects_symlink_and_bounded_size(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "contract.json"
            path.write_bytes(b"{}")
            symlink = Path(directory) / "linked.json"
            symlink.symlink_to(path)
            with self.assertRaises((OSError, ValueError)):
                GUARD.validate_json_source(symlink)
            with self.assertRaisesRegex(ValueError, "size bound"):
                GUARD.validate_json_source(path, max_bytes=1)


if __name__ == "__main__":
    unittest.main()
