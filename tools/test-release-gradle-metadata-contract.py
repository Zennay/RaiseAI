#!/usr/bin/env python3
"""Fail closed if the release label and Android package identity drift apart."""
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]


def unique(pattern: str, source: str, label: str) -> str:
    matches = re.findall(pattern, source, flags=re.MULTILINE)
    if len(matches) != 1:
        raise AssertionError(f"{label}: expected exactly one declaration, found {len(matches)}")
    return matches[0]


class ReleaseMetadataContract(unittest.TestCase):
    def test_version_name_matches_canonical_version(self):
        version = (ROOT / "VERSION.txt").read_text(encoding="utf-8").strip()
        self.assertRegex(version, r"^\d+\.\d+\.\d+$")
        gradle = (ROOT / "app/build.gradle.kts").read_text(encoding="utf-8")
        declared = unique(r'^\s*versionName\s*=\s*"([^"]+)"\s*$', gradle, "versionName")
        self.assertEqual(version, declared)

    def test_version_code_is_single_positive_integer(self):
        gradle = (ROOT / "app/build.gradle.kts").read_text(encoding="utf-8")
        code = unique(r'^\s*versionCode\s*=\s*(\S+)\s*$', gradle, "versionCode")
        self.assertRegex(code, r"^[1-9][0-9]*$")

    def test_release_readme_matches_package_version_and_code(self):
        version = (ROOT / "VERSION.txt").read_text(encoding="utf-8").strip()
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        gradle = (ROOT / "app/build.gradle.kts").read_text(encoding="utf-8")
        code = unique(r'^\s*versionCode\s*=\s*(\S+)\s*$', gradle, "versionCode")
        heading = readme.splitlines()[0]
        self.assertEqual(heading, f"# Raise AI v{version} — Galaxy Watch 7")
        self.assertIn(f"- v{version} uses versionCode {code}.", readme)


if __name__ == "__main__":
    unittest.main()
