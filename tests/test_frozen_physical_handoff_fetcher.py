import hashlib
import importlib.util
import io
import os
import sys
import tempfile
import unittest
import urllib.request
from unittest import mock
import warnings
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

    def test_cross_origin_release_redirect_strips_authorization(self):
        request = urllib.request.Request(
            MODULE.ASSET_API_URL,
            headers={
                "Authorization": "Bearer secret-test-token",
                "Accept": "application/octet-stream",
            },
        )

        redirected = MODULE._SafeReleaseRedirect().redirect_request(
            request,
            None,
            302,
            "Found",
            {},
            "https://release-assets.githubusercontent.com/example/handoff.zip",
        )

        self.assertIsNotNone(redirected)
        self.assertIsNone(redirected.get_header("Authorization"))
        self.assertEqual(
            redirected.get_header("Accept"),
            "application/octet-stream",
        )

    def test_same_origin_release_redirect_keeps_authorization(self):
        request = urllib.request.Request(
            MODULE.ASSET_API_URL,
            headers={"Authorization": "Bearer secret-test-token"},
        )

        redirected = MODULE._SafeReleaseRedirect().redirect_request(
            request,
            None,
            302,
            "Found",
            {},
            "https://api.github.com/repos/Zennay/RaiseAI/releases/assets/611084738?download=1",
        )

        self.assertIsNotNone(redirected)
        self.assertEqual(
            redirected.get_header("Authorization"),
            "Bearer secret-test-token",
        )

    def test_release_redirect_rejects_https_downgrade(self):
        request = urllib.request.Request(
            MODULE.ASSET_API_URL,
            headers={"Authorization": "Bearer secret-test-token"},
        )

        with self.assertRaisesRegex(MODULE.HandoffError, "non-HTTPS"):
            MODULE._SafeReleaseRedirect().redirect_request(
                request,
                None,
                302,
                "Found",
                {},
                "http://release-assets.githubusercontent.com/example/handoff.zip",
            )

    def test_download_accepts_exact_frozen_asset_size(self):
        with tempfile.TemporaryDirectory() as tmp:
            destination = Path(tmp) / "handoff.zip"
            opener = mock.Mock()
            opener.open.return_value = io.BytesIO(b"test")

            with mock.patch.object(
                MODULE,
                "EXPECTED_ARCHIVE_SIZE_BYTES",
                4,
            ), mock.patch.object(
                urllib.request,
                "build_opener",
                return_value=opener,
            ):
                MODULE.download_release_asset(destination)

            self.assertEqual(destination.read_bytes(), b"test")

    def test_download_rejects_oversized_asset_and_removes_partial_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            destination = Path(tmp) / "handoff.zip"
            opener = mock.Mock()
            opener.open.return_value = io.BytesIO(b"12345")

            with mock.patch.object(
                MODULE,
                "EXPECTED_ARCHIVE_SIZE_BYTES",
                4,
            ), mock.patch.object(
                urllib.request,
                "build_opener",
                return_value=opener,
            ):
                with self.assertRaisesRegex(MODULE.HandoffError, "exceeded expected size"):
                    MODULE.download_release_asset(destination)

            self.assertFalse(destination.exists())

    def test_download_rejects_truncated_asset_and_removes_partial_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            destination = Path(tmp) / "handoff.zip"
            opener = mock.Mock()
            opener.open.return_value = io.BytesIO(b"123")

            with mock.patch.object(
                MODULE,
                "EXPECTED_ARCHIVE_SIZE_BYTES",
                4,
            ), mock.patch.object(
                urllib.request,
                "build_opener",
                return_value=opener,
            ):
                with self.assertRaisesRegex(MODULE.HandoffError, "size mismatch"):
                    MODULE.download_release_asset(destination)

            self.assertFalse(destination.exists())

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

    def test_rejects_dot_alias_that_collides_with_required_member(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            archive = self._build_archive(root)
            with zipfile.ZipFile(archive, "a") as package:
                package.writestr("./BUILD-IDENTITY.txt", b"shadowed\n")
            expected = hashlib.sha256(archive.read_bytes()).hexdigest()
            output = root / "verified"

            with self.assertRaisesRegex(MODULE.HandoffError, "Unsafe archive member path"):
                MODULE.extract_verified_archive(
                    archive,
                    output,
                    expected_sha256=expected,
                )

            self.assertFalse(output.exists())

    def test_rejects_backslash_archive_member_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            archive = self._build_archive(root)
            with zipfile.ZipFile(archive, "a") as package:
                package.writestr(r"nested\\alias.txt", b"ambiguous")
            expected = hashlib.sha256(archive.read_bytes()).hexdigest()
            output = root / "verified"

            with self.assertRaisesRegex(MODULE.HandoffError, "Unsafe archive member path"):
                MODULE.extract_verified_archive(
                    archive,
                    output,
                    expected_sha256=expected,
                )

            self.assertFalse(output.exists())

    def test_rejects_casefold_collision_with_required_member(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            archive = self._build_archive(root)
            with zipfile.ZipFile(archive, "a") as package:
                package.writestr("build-identity.txt", b"shadowed\n")
            expected = hashlib.sha256(archive.read_bytes()).hexdigest()
            output = root / "verified"

            with self.assertRaisesRegex(MODULE.HandoffError, "portable path collision"):
                MODULE.extract_verified_archive(
                    archive,
                    output,
                    expected_sha256=expected,
                )

            self.assertFalse(output.exists())

    def test_rejects_unicode_normalization_path_collision(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            archive = self._build_archive(root)
            with zipfile.ZipFile(archive, "a") as package:
                package.writestr("notes/\u00e9.txt", b"first")
                package.writestr("notes/e\u0301.txt", b"second")
            expected = hashlib.sha256(archive.read_bytes()).hexdigest()
            output = root / "verified"

            with self.assertRaisesRegex(MODULE.HandoffError, "portable path collision"):
                MODULE.extract_verified_archive(
                    archive,
                    output,
                    expected_sha256=expected,
                )

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

    def test_refuses_dangling_output_symlink_without_creating_target(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            archive = self._build_archive(root)
            expected = hashlib.sha256(archive.read_bytes()).hexdigest()
            output = root / "verified"
            target = root / "unexpected-target"
            output.symlink_to(target, target_is_directory=True)

            with self.assertRaisesRegex(MODULE.HandoffError, "refusing to overwrite"):
                MODULE.extract_verified_archive(
                    archive,
                    output,
                    expected_sha256=expected,
                )

            self.assertTrue(output.is_symlink())
            self.assertFalse(target.exists())

    def test_main_preserves_output_path_without_following_symlink(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            archive = root / "handoff.zip"
            archive.write_bytes(b"placeholder")
            output = root / "verified"
            target = root / "unexpected-target"
            output.symlink_to(target, target_is_directory=True)

            with mock.patch.object(
                sys,
                "argv",
                [str(MODULE_PATH), "--archive", str(archive), "--output", str(output)],
            ), mock.patch.object(MODULE, "extract_verified_archive") as extract:
                code = MODULE.main()

            self.assertEqual(code, 0)
            extract.assert_called_once()
            passed_output = extract.call_args.args[1]
            self.assertEqual(os.fspath(passed_output), os.fspath(output.absolute()))
            self.assertNotEqual(os.fspath(passed_output), os.fspath(target.absolute()))

    def test_rejects_duplicate_archive_member_names(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            archive = self._build_archive(root)
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", UserWarning)
                with zipfile.ZipFile(archive, "a") as package:
                    package.writestr("BUILD-IDENTITY.txt", b"shadowed\n")
            expected = hashlib.sha256(archive.read_bytes()).hexdigest()
            output = root / "verified"

            with self.assertRaisesRegex(MODULE.HandoffError, "duplicate archive members"):
                MODULE.extract_verified_archive(
                    archive,
                    output,
                    expected_sha256=expected,
                )

            self.assertFalse(output.exists())

    def test_failed_atomic_publish_leaves_no_partial_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            archive = self._build_archive(root)
            expected = hashlib.sha256(archive.read_bytes()).hexdigest()
            output = root / "verified"

            with mock.patch.object(Path, "rename", side_effect=OSError("simulated publish failure")):
                with self.assertRaisesRegex(
                    MODULE.HandoffError,
                    "Could not publish verified handoff atomically",
                ):
                    MODULE.extract_verified_archive(
                        archive,
                        output,
                        expected_sha256=expected,
                    )

            self.assertFalse(output.exists())
            self.assertFalse(
                any(path.name.startswith(".verified.") for path in root.iterdir())
            )

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
