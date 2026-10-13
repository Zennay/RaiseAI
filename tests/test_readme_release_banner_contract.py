#!/usr/bin/env python3
"""Ensure the public README release banner tracks the canonical Watch version."""
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]


def verify_banner(version_text: str, readme_text: str) -> None:
    version = version_text.strip()
    if not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", version):
        raise ValueError("VERSION.txt must be a single numeric semantic version")
    lines = readme_text.splitlines()
    if not lines:
        raise ValueError("README.md is empty")
    expected = f"# Raise AI v{version} — Galaxy Watch 7"
    if lines[0] != expected:
        raise ValueError(f"README release banner mismatch: expected {expected!r}")


class ReadmeReleaseBannerContract(unittest.TestCase):
    def test_current_repository_release_banner(self):
        verify_banner((ROOT / "VERSION.txt").read_text(encoding="utf-8"),
                      (ROOT / "README.md").read_text(encoding="utf-8"))

    def test_mismatch_fails(self):
        with self.assertRaisesRegex(ValueError, "banner mismatch"):
            verify_banner("1.5.3\n", "# Raise AI v1.5.2 — Galaxy Watch 7\n")

    def test_nonversion_fails(self):
        for invalid in ("", "unknown", "1.5.3\n1.5.4", "v1.5.3"):
            with self.subTest(invalid=invalid):
                with self.assertRaisesRegex(ValueError, "semantic version"):
                    verify_banner(invalid, "# Raise AI v1.5.3 — Galaxy Watch 7")

    def test_banner_must_be_first_line(self):
        with self.assertRaisesRegex(ValueError, "banner mismatch"):
            verify_banner("1.5.3", "\n# Raise AI v1.5.3 — Galaxy Watch 7")


if __name__ == "__main__":
    unittest.main()
