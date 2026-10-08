"""Fail-closed regression cases for physical observation evidence ingestion.

These tests exercise file types and nested JSON ambiguity independently of Watch
hardware. They must never install, provision, or modify the frozen v1.5.2 handoff.
"""
import importlib.util
import json
import os
from pathlib import Path
import socket
import tempfile
import unittest

SOURCE = Path(__file__).resolve().parents[1] / "tools" / "validate-physical-observations.py"
SPEC = importlib.util.spec_from_file_location("observation_input_type_contract", SOURCE)
validator = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(validator)


class ObservationInputTypeContract(unittest.TestCase):
    @unittest.skipUnless(hasattr(os, "mkfifo"), "FIFOs unavailable on host")
    def test_fifo_evidence_rejected_without_waiting_for_writer(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "session.json"
            os.mkfifo(path)
            with self.assertRaisesRegex(validator.ObservationError, "must be a regular file"):
                validator.load_json_document(path, "session")

    @unittest.skipUnless(hasattr(socket, "AF_UNIX"), "Unix sockets unavailable on host")
    def test_socket_evidence_rejected_without_consuming_stream(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "observations.json"
            with socket.socket(socket.AF_UNIX) as listener:
                listener.bind(str(path))
                with self.assertRaises(OSError):
                    validator.load_json_document(path, "observations")

    def test_nested_duplicate_fields_rejected_even_when_top_level_is_unique(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "session.json"
            path.write_text('{"nested":{"serial":"first","serial":"second"}}', encoding="utf-8")
            with self.assertRaisesRegex(validator.ObservationError, "duplicate JSON field: serial"):
                validator.load_json_document(path, "session")

    def test_maximum_input_byte_boundary_is_inclusive(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "session.json"
            encoded = json.dumps({"padding": "x" * (validator.MAX_JSON_BYTES - len('{"padding": ""}'))})
            self.assertEqual(len(encoded.encode("utf-8")), validator.MAX_JSON_BYTES)
            path.write_bytes(encoded.encode("utf-8"))
            self.assertEqual(validator.load_json_document(path, "session")["padding"][:1], "x")

    def test_oversized_input_is_rejected_before_json_parsing(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "observations.json"
            path.write_bytes(b" " * (validator.MAX_JSON_BYTES + 1))
            with self.assertRaisesRegex(validator.ObservationError, "exceeds maximum size"):
                validator.load_json_document(path, "observations")


if __name__ == "__main__":
    unittest.main()
