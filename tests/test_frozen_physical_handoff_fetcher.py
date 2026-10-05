import hashlib
import importlib.util
import tempfile
import unittest
import zipfile
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "tools" / "fetch-frozen-physical-handoff.py"
SPEC = importlib.util.spec_from_file_location("frozen_handoff", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


class FrozenHandoffFetcherTests(unittest.TestCase):
    def _build_archive(self, root: Path, *, unsafe: bool = False, missing: str | None = None) -> Path:
        archive = root / "handoff.zip"
        members = {
            "BUILD-IDENTITY.txt": b"source_revision=test\n",
            "RaiseAI-v1.5.2-debug.apk": b"apk",
            "RaiseAI-v1.5.2-source.bundle": b"bundle",
            "start-physical-handoff.command": b"#!/bin/bash\necho ok\n",
        }
        if missing:
            members.pop(missing)

        with zipfile.ZipFile(archive, "w") as package:
            for name, payload in members.items():
                package.writestr(name, payload)
            if unsafe:
                package.writestr("../escape.txt", b"nope")
        return archive

    def test_extracts_only_after_matching_archive_digest(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            archive = self._build_archive(root)
            expected = hashlib.sha256(archive.read_bytes()).hexdigest()
            output = root / "verified"

            MODULE.extract_verified_archive(
                archive,
                output,
                expected_sha256=expected,
            )

            self.assertTrue((output / "BUILD-IDENTITY.txt").is_file())
            self.assertTrue((output / "RaiseAI-v1.5.2-debug.apk").is_file())
            self.assertTrue((output / "RaiseAI-v1.5.2-source.bundle").is_file())
            self.assertTrue((output / "start-physical-handoff.command").is_file())

    def test_rejects_digest_mismatch_before_extracting(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            archive = self._build_archive(root)
            output = root / "verified"

            with self.assertRaisesRegex(MODULE.HandoffError, "SHA-256 mismatch"):
                MODULE.extract_verified_archive(
                    archive,
                    output,
                    expected_sha256="0" * 64,
                )

            self.assertFalse(output.exists())

    def test_rejects_path_traversal(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            archive = self._build_archive(root, unsafe=True)
            expected = hashlib.sha256(archive.read_bytes()).hexdigest()
            output = root / "verified"

            with self.assertRaisesRegex(MODULE.HandoffError, "Unsafe archive member path"):
                MODULE.extract_verified_archive(
                    archive,
                    output,
                    expected_sha256=expected,
                )

            self.assertFalse((root / "escape.txt").exists())
            self.assertFalse(output.exists())

    def test_rejects_missing_required_member(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            archive = self._build_archive(root, missing="RaiseAI-v1.5.2-debug.apk")
            expected = hashlib.sha256(archive.read_bytes()).hexdigest()
            output = root / "verified"

            with self.assertRaisesRegex(MODULE.HandoffError, "missing required members"):
                MODULE.extract_verified_archive(
                    archive,
                    output,
                    expected_sha256=expected,
                )

            self.assertFalse(output.exists())

    def test_refuses_to_overwrite_existing_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            archive = self._build_archive(root)
            expected = hashlib.sha256(archive.read_bytes()).hexdigest()
            output = root / "verified"
            output.mkdir()

            with self.assertRaisesRegex(MODULE.HandoffError, "refusing to overwrite"):
                MODULE.extract_verified_archive(
                    archive,
                    output,
                    expected_sha256=expected,
                )


if __name__ == "__main__":
    unittest.main()
