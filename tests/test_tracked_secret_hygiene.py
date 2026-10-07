from pathlib import Path, PurePosixPath
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[1]

FORBIDDEN_BASENAMES = {
    "local.properties",
    "secrets.properties",
    "keystore.properties",
    "signing.properties",
    "credentials.json",
    "gateway.env",
    "watch-gateway.properties",
}
FORBIDDEN_SUFFIXES = {
    ".jks",
    ".keystore",
    ".p12",
    ".pfx",
    ".pem",
    ".key",
}
ALLOWED_ENV_TEMPLATES = {".env.example", ".env.sample"}

PRIVATE_KEY_MARKERS = (
    b"-----BEGIN " + b"PRIVATE KEY-----",
    b"-----BEGIN " + b"ENCRYPTED PRIVATE KEY-----",
    b"-----BEGIN " + b"RSA PRIVATE KEY-----",
    b"-----BEGIN " + b"EC PRIVATE KEY-----",
    b"-----BEGIN " + b"OPENSSH PRIVATE KEY-----",
)


def tracked_paths() -> list[str]:
    result = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
    )
    return [
        raw.decode("utf-8", errors="strict")
        for raw in result.stdout.split(b"\0")
        if raw
    ]


class TrackedSecretHygieneTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.paths = tracked_paths()

    def test_forbidden_local_secret_files_are_not_tracked(self):
        offenders = []
        for raw in self.paths:
            path = PurePosixPath(raw)
            name = path.name.lower()

            if name in FORBIDDEN_BASENAMES:
                offenders.append(raw)
                continue

            if name == ".env" or (
                name.startswith(".env.") and name not in ALLOWED_ENV_TEMPLATES
            ):
                offenders.append(raw)
                continue

            if any(name.endswith(suffix) for suffix in FORBIDDEN_SUFFIXES):
                offenders.append(raw)
                continue

            lowered_parts = tuple(part.lower() for part in path.parts)
            if ".raiseai" in lowered_parts:
                offenders.append(raw)
                continue

            if len(lowered_parts) >= 2:
                for index in range(len(lowered_parts) - 1):
                    if lowered_parts[index:index + 2] == (".config", "raiseai"):
                        offenders.append(raw)
                        break

        self.assertEqual(
            sorted(set(offenders)),
            [],
            "local secret/config material must never be tracked; use documented templates instead",
        )

    def test_tracked_files_do_not_contain_private_key_headers(self):
        offenders = []
        for raw in self.paths:
            path = ROOT / raw
            if not path.is_file():
                continue

            # Private-key PEM/OpenSSH headers are tiny and always near text content.
            # Bound reads so this contract never loads an unexpectedly large artifact.
            try:
                with path.open("rb") as handle:
                    payload = handle.read(2 * 1024 * 1024 + 1)
            except OSError as exc:
                self.fail(f"could not inspect tracked path {raw}: {exc}")

            if len(payload) > 2 * 1024 * 1024:
                continue

            if any(marker in payload for marker in PRIVATE_KEY_MARKERS):
                offenders.append(raw)

        self.assertEqual(
            offenders,
            [],
            "tracked private-key material is forbidden",
        )

    def test_gitignore_retains_defense_in_depth_patterns(self):
        text = (ROOT / ".gitignore").read_text(encoding="utf-8")
        required = (
            ".env",
            ".env.*",
            "local.properties",
            "secrets.properties",
            "keystore.properties",
            "signing.properties",
            "credentials.json",
            "*.jks",
            "*.keystore",
            "*.p12",
            "*.pfx",
            "*.pem",
            "*.key",
        )
        for pattern in required:
            with self.subTest(pattern=pattern):
                self.assertEqual(
                    text.splitlines().count(pattern),
                    1,
                    f".gitignore must retain secret defense-in-depth pattern {pattern}",
                )


if __name__ == "__main__":
    unittest.main()
