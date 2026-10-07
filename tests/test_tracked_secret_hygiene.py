from pathlib import Path, PurePosixPath
import inspect
import re
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
    "-----BEGIN " + "PRIVATE KEY-----",
    "-----BEGIN " + "ENCRYPTED PRIVATE KEY-----",
    "-----BEGIN " + "RSA PRIVATE KEY-----",
    "-----BEGIN " + "EC PRIVATE KEY-----",
    "-----BEGIN " + "OPENSSH PRIVATE KEY-----",
)

HIGH_CONFIDENCE_SECRET_PATTERNS = (
    r"sk-or-v1-[A-Za-z0-9_-]{32,}",
    r"sk-proj-[A-Za-z0-9_-]{32,}",
    r"github_pat_[A-Za-z0-9_]{50,}",
    r"gh[pousr]_[A-Za-z0-9]{36,}",
    r"AIza[0-9A-Za-z_-]{35}",
    r"AKIA[0-9A-Z]{16}",
)


def run_git(args: list[str]) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        ["git", *args],
        cwd=ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )


def tracked_paths() -> list[str]:
    result = run_git(["ls-files", "-z"])
    if result.returncode != 0:
        raise RuntimeError(
            f"git ls-files failed with exit {result.returncode}: "
            f"{result.stderr.decode('utf-8', errors='replace').strip()}"
        )
    return [
        raw.decode("utf-8", errors="strict")
        for raw in result.stdout.split(b"\0")
        if raw
    ]


def cached_grep_paths(patterns: tuple[str, ...], *, extended: bool) -> list[str]:
    args = ["grep", "--cached", "-I", "-l", "-z"]
    args.append("-E" if extended else "-F")
    for pattern in patterns:
        args.extend(["-e", pattern])
    args.extend(["--", "."])

    result = run_git(args)
    if result.returncode == 1:
        return []
    if result.returncode != 0:
        raise RuntimeError(
            f"git grep failed with exit {result.returncode}: "
            f"{result.stderr.decode('utf-8', errors='replace').strip()}"
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

    def test_git_index_blobs_do_not_contain_private_key_headers(self):
        offenders = cached_grep_paths(PRIVATE_KEY_MARKERS, extended=False)
        self.assertEqual(
            offenders,
            [],
            "tracked private-key material is forbidden",
        )

    def test_git_index_blobs_do_not_contain_high_confidence_tokens(self):
        offenders = cached_grep_paths(
            HIGH_CONFIDENCE_SECRET_PATTERNS,
            extended=True,
        )
        self.assertEqual(
            offenders,
            [],
            "tracked credential-like tokens are forbidden",
        )

    def test_high_confidence_token_patterns_reject_real_shapes_not_placeholders(self):
        synthetic_tokens = (
            "sk-or-" + "v1-" + ("a" * 64),
            "sk-" + "proj-" + ("b" * 48),
            "github_" + "pat_" + ("C" * 60),
            "gh" + "p_" + ("D" * 36),
            "AI" + "za" + ("E" * 35),
            "AK" + "IA" + ("F" * 16),
        )
        combined = re.compile("|".join(f"(?:{pattern})" for pattern in HIGH_CONFIDENCE_SECRET_PATTERNS))
        for token in synthetic_tokens:
            with self.subTest(prefix=token[:8]):
                self.assertIsNotNone(combined.search(token))

        for placeholder in (
            "sk-or-" + "v1-...",
            "sk-" + "proj-...",
            "github_" + "pat_EXAMPLE",
            "gh" + "p_EXAMPLE",
            "AI" + "zaEXAMPLE",
            "AK" + "IAEXAMPLE",
        ):
            with self.subTest(placeholder=placeholder):
                self.assertIsNone(combined.search(placeholder))

    def test_secret_content_scan_uses_git_index_not_worktree_reads(self):
        source = inspect.getsource(cached_grep_paths)
        self.assertIn('"grep", "--cached"', source)
        self.assertNotIn(".open(", source)
        self.assertNotIn(".is_file()", source)

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
