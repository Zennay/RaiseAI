import hashlib
import importlib.util
import io
import pathlib
import tempfile
import unittest
import zipfile
from unittest import mock

MODULE_PATH = pathlib.Path(__file__).resolve().parents[1] / "tools" / "verify-watch-apk-identity.py"
SPEC = importlib.util.spec_from_file_location("watch_apk_identity", MODULE_PATH)
verifier = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(verifier)

REVISION = "0123456789abcdef0123456789abcdef01234567"


def make_apk(
    path: pathlib.Path,
    *,
    revision: str = REVISION,
    abi: str = "armeabi-v7a",
    dex_payload: bytes | None = None,
) -> str:
    payload = (
        dex_payload
        if dex_payload is not None
        else b"dex-prefix-" + revision.encode("ascii") + b"-dex-suffix"
    )
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("classes.dex", payload)
        archive.writestr(f"lib/{abi}/libraise.so", b"native")
    return hashlib.sha256(path.read_bytes()).hexdigest()


class WatchApkIdentityTests(unittest.TestCase):
    def test_accepts_exact_digest_revision_and_watch_abi(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / "RaiseAI.apk"
            digest = make_apk(path)
            report = verifier.verify_apk(
                path,
                expected_source_revision=REVISION,
                expected_sha256=digest,
            )
            self.assertTrue(report["valid"])
            self.assertEqual(report["apk_sha256"], digest)
            self.assertEqual(report["source_revision"], REVISION)
            self.assertEqual(report["abis"], ["armeabi-v7a"])

    def test_rejects_wrong_digest(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / "RaiseAI.apk"
            make_apk(path)
            with self.assertRaisesRegex(verifier.ApkIdentityError, "SHA-256 mismatch"):
                verifier.verify_apk(
                    path,
                    expected_source_revision=REVISION,
                    expected_sha256="f" * 64,
                )

    def test_rejects_wrong_source_revision(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / "RaiseAI.apk"
            make_apk(path)
            with self.assertRaisesRegex(verifier.ApkIdentityError, "not embedded"):
                verifier.verify_apk(
                    path,
                    expected_source_revision="a" * 40,
                )

    def test_rejects_wrong_abi(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / "RaiseAI.apk"
            make_apk(path, abi="arm64-v8a")
            with self.assertRaisesRegex(verifier.ApkIdentityError, "ABI set mismatch"):
                verifier.verify_apk(
                    path,
                    expected_source_revision=REVISION,
                )

    def test_rejects_invalid_apk_archive(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / "RaiseAI.apk"
            path.write_text("not an apk", encoding="utf-8")
            with self.assertRaisesRegex(verifier.ApkIdentityError, "valid ZIP"):
                verifier.verify_apk(
                    path,
                    expected_source_revision=REVISION,
                )

    def test_streamed_revision_scan_finds_sha_across_chunk_boundary(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / "RaiseAI.apk"
            prefix = b"x" * (verifier.DEX_SCAN_CHUNK_BYTES - 20)
            make_apk(
                path,
                dex_payload=prefix + REVISION.encode("ascii") + b"-tail",
            )

            report = verifier.verify_apk(
                path,
                expected_source_revision=REVISION,
            )

            self.assertTrue(report["valid"])
            self.assertEqual(report["revision_dex_files"], ["classes.dex"])

    def test_revision_scan_never_requests_unbounded_member_read(self):
        class RecordingMember(io.BytesIO):
            def __init__(self, payload: bytes):
                super().__init__(payload)
                self.read_sizes: list[int] = []

            def read(self, size: int = -1) -> bytes:
                self.read_sizes.append(size)
                return super().read(size)

        class Archive:
            def __init__(self, member: RecordingMember):
                self.member = member

            def open(self, name: str, mode: str):
                self.assertions = (name, mode)
                return self.member

        payload = (
            b"x" * (verifier.DEX_SCAN_CHUNK_BYTES - 10)
            + REVISION.encode("ascii")
            + b"-tail"
        )
        member = RecordingMember(payload)
        archive = Archive(member)

        self.assertTrue(
            verifier._zip_member_contains(
                archive,
                "classes.dex",
                REVISION.encode("ascii"),
            )
        )
        self.assertEqual(archive.assertions, ("classes.dex", "r"))
        self.assertTrue(member.read_sizes)
        self.assertNotIn(-1, member.read_sizes)
        self.assertTrue(
            all(size == verifier.DEX_SCAN_CHUNK_BYTES for size in member.read_sizes)
        )

    def test_hash_and_archive_inspection_use_same_open_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            path = root / "RaiseAI.apk"
            replacement = root / "replacement.apk"
            digest = make_apk(path)
            make_apk(replacement, revision="f" * 40)

            real_hash = verifier._sha256_open_file

            def hash_then_replace(apk_file):
                result = real_hash(apk_file)
                path.unlink()
                replacement.rename(path)
                return result

            with mock.patch.object(verifier, "_sha256_open_file", side_effect=hash_then_replace):
                report = verifier.verify_apk(
                    path,
                    expected_source_revision=REVISION,
                    expected_sha256=digest,
                )

            self.assertEqual(report["apk_sha256"], digest)
            with zipfile.ZipFile(path) as archive:
                self.assertIn(("f" * 40).encode("ascii"), archive.read("classes.dex"))

    def test_rejects_symlink_apk(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            target = root / "real.apk"
            make_apk(target)
            path = root / "RaiseAI.apk"
            path.symlink_to(target)
            with self.assertRaisesRegex(verifier.ApkIdentityError, "opened safely"):
                verifier.verify_apk(
                    path,
                    expected_source_revision=REVISION,
                )


if __name__ == "__main__":
    unittest.main()
