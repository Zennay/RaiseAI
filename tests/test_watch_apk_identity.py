import hashlib
import importlib.util
import pathlib
import tempfile
import unittest
import zipfile

MODULE_PATH = pathlib.Path(__file__).resolve().parents[1] / "tools" / "verify-watch-apk-identity.py"
SPEC = importlib.util.spec_from_file_location("watch_apk_identity", MODULE_PATH)
verifier = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(verifier)

REVISION = "0123456789abcdef0123456789abcdef01234567"


def make_apk(path: pathlib.Path, *, revision: str = REVISION, abi: str = "armeabi-v7a") -> str:
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("classes.dex", b"dex-prefix-" + revision.encode("ascii") + b"-dex-suffix")
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


if __name__ == "__main__":
    unittest.main()
