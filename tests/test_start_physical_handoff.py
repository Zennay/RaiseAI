import hashlib
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
STARTER = ROOT / "start-physical-handoff.command"


def run(*args, cwd=None, env=None, check=True):
    return subprocess.run(
        [str(arg) for arg in args],
        cwd=cwd,
        env=env,
        check=check,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )


class StartPhysicalHandoffTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.artifact = self.root / "handoff"
        self.artifact.mkdir()
        shutil.copy2(STARTER, self.artifact / STARTER.name)

        source = self.root / "source"
        source.mkdir()
        run("git", "init", "-q", source)
        run("git", "-C", source, "config", "user.email", "raiseai-ci@example.invalid")
        run("git", "-C", source, "config", "user.name", "RaiseAI CI")
        verifier = source / "tools" / "verify-watch-apk-identity.py"
        verifier.parent.mkdir()
        verifier.write_text(
            "import json\nprint(json.dumps({'ok': True}))\n",
            encoding="utf-8",
        )
        run("git", "-C", source, "add", ".")
        run("git", "-C", source, "commit", "-qm", "fixture")
        run("git", "-C", source, "branch", "-M", "handoff")
        self.revision = run("git", "-C", source, "rev-parse", "HEAD").stdout.strip().lower()

        self.bundle = self.artifact / "RaiseAI-v1.5.2-source.bundle"
        run("git", "-C", source, "bundle", "create", self.bundle, "handoff")

        self.apk = self.artifact / "RaiseAI-v1.5.2-debug.apk"
        self.apk.write_bytes(b"raiseai-test-apk")
        apk_sha = hashlib.sha256(self.apk.read_bytes()).hexdigest()
        bundle_sha = hashlib.sha256(self.bundle.read_bytes()).hexdigest()
        (self.artifact / "BUILD-IDENTITY.txt").write_text(
            f"source_revision={self.revision}\n"
            f"apk_sha256={apk_sha}\n"
            f"source_bundle_sha256={bundle_sha}\n",
            encoding="utf-8",
        )
        self.restore = self.root / "restore"

    def tearDown(self):
        self.temp.cleanup()

    def starter(self, restore=None):
        env = os.environ.copy()
        env["RAISE_RESTORE_DIR"] = str(restore or self.restore)
        return run(
            "bash",
            self.artifact / "start-physical-handoff.command",
            "--verify-only",
            env=env,
            check=False,
        )

    def test_clean_exact_restore_is_retry_safe(self):
        first = self.starter()
        self.assertEqual(first.returncode, 0, first.stdout)
        self.assertIn("VERIFY-ONLY PASS", first.stdout)

        second = self.starter()
        self.assertEqual(second.returncode, 0, second.stdout)
        self.assertIn("Reusing exact clean restored source:", second.stdout)
        self.assertIn("VERIFY-ONLY PASS", second.stdout)

    def test_tampered_apk_fails_before_bundled_verifier(self):
        self.apk.write_bytes(b"tampered-raiseai-test-apk")

        result = self.starter()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("APK SHA-256 mismatch.", result.stdout)
        self.assertFalse(self.restore.exists())

    def test_duplicate_source_revision_fails_closed(self):
        identity = self.artifact / "BUILD-IDENTITY.txt"
        identity.write_text(
            identity.read_text(encoding="utf-8")
            + f"source_revision={self.revision}\n",
            encoding="utf-8",
        )

        result = self.starter()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(
            "must contain exactly one non-empty source_revision= entry (found 2)",
            result.stdout,
        )
        self.assertFalse(self.restore.exists())

    def test_duplicate_digest_key_fails_closed(self):
        identity = self.artifact / "BUILD-IDENTITY.txt"
        apk_sha = hashlib.sha256(self.apk.read_bytes()).hexdigest()
        identity.write_text(
            identity.read_text(encoding="utf-8") + f"apk_sha256={apk_sha}\n",
            encoding="utf-8",
        )

        result = self.starter()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(
            "must contain exactly one non-empty apk_sha256= entry (found 2)",
            result.stdout,
        )
        self.assertFalse(self.restore.exists())

    def test_existing_non_git_restore_fails_closed(self):
        path = self.root / "not-a-checkout"
        path.mkdir()
        result = self.starter(path)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Restore path exists but is not a Git checkout", result.stdout)

    def test_dirty_restore_fails_closed(self):
        first = self.starter()
        self.assertEqual(first.returncode, 0, first.stdout)
        (self.restore / "dirty.txt").write_text("dirty\n", encoding="utf-8")

        result = self.starter()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Existing restore checkout is dirty", result.stdout)

    def test_wrong_revision_restore_fails_closed(self):
        first = self.starter()
        self.assertEqual(first.returncode, 0, first.stdout)
        run("git", "-C", self.restore, "config", "user.email", "raiseai-ci@example.invalid")
        run("git", "-C", self.restore, "config", "user.name", "RaiseAI CI")
        (self.restore / "later.txt").write_text("later\n", encoding="utf-8")
        run("git", "-C", self.restore, "add", "later.txt")
        run("git", "-C", self.restore, "commit", "-qm", "different revision")

        result = self.starter()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Existing restore revision does not match the handoff.", result.stdout)


if __name__ == "__main__":
    unittest.main()
