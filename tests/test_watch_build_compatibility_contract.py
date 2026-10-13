#!/usr/bin/env python3
"""Source-only build compatibility gate for Galaxy Watch 7 releases.

Watch CI's verifyWatchAbi task checks the built APK. This separate lightweight
contract makes Gradle configuration drift visible before hardware validation.
It never substitutes for an assembled APK or a physical Watch 7 test.
"""
from pathlib import Path
import re
import unittest

BUILD = Path(__file__).resolve().parents[1] / "app/build.gradle.kts"

PINNED = {
    "namespace": '"nl.zennay.raiseai"',
    "applicationId": '"nl.zennay.raiseai"',
    "compileSdk": "35",
    "minSdk": "30",
    "targetSdk": "35",
}
WATCH_ABI = "armeabi-v7a"


def assignments(source: str, key: str) -> list[str]:
    return re.findall(
        r"(?m)^[ \t]*" + re.escape(key) + r"[ \t]*=[ \t]*([^\r\n]+?)[ \t]*$",
        source,
    )


def compatibility_violations(source: str) -> list[str]:
    errors: list[str] = []
    for key, expected in PINNED.items():
        values = assignments(source, key)
        if values != [expected]:
            errors.append(f"{key}: expected one exact {expected} assignment; found {values!r}")

    # Inspect all active abiFilters lines, not only matching += declarations:
    # a second +=, assignment/setOf() or disabling the filter must fail.
    abi_lines = re.findall(r"(?m)^[ \t]*abiFilters\b[^\r\n]*$", source)
    expected_abi_line = f'abiFilters += "{WATCH_ABI}"'
    if [line.strip() for line in abi_lines] != [expected_abi_line]:
        errors.append(f"Watch ABI filter must be exactly {expected_abi_line}")

    checks = {
        "buildConfig generation": r"(?m)^[ \t]*buildConfig[ \t]*=[ \t]*true[ \t]*$",
        "source revision in BuildConfig": (
            r'(?m)^[ \t]*buildConfigField\("String", "SOURCE_REVISION", '
            r'"\\\"\$sourceRevision\\\""\)[ \t]*$'
        ),
        "APK ABI verification task": r'(?m)^[ \t]*tasks\.register\("verifyWatchAbi"\)[ \t]*\{[ \t]*$',
        "APK ABI verification called after assembleDebug": (
            r'(?m)^[ \t]*finalizedBy\("verifyWatchAbi"\)[ \t]*$'
        ),
        "APK ABI verifier compares exact ABI set": (
            r'(?m)^[ \t]*check\(abis == expected\)[ \t]*\{[ \t]*$'
        ),
    }
    for label, pattern in checks.items():
        if len(re.findall(pattern, source)) != 1:
            errors.append(f"{label}: expected exactly one active declaration")

    # This should be an exact runtime comparison in verifyWatchAbi rather than
    # solely a comment documenting an intended ABI.
    if len(re.findall(r'(?m)^[ \t]*val expected = setOf\("armeabi-v7a"\)[ \t]*$', source)) != 1:
        errors.append("APK verifier must expect exactly armeabi-v7a")
    return errors


class WatchBuildCompatibilityContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.original = BUILD.read_text(encoding="utf-8")

    def changed(self, old, new):
        self.assertIn(old, self.original)
        return compatibility_violations(self.original.replace(old, new, 1))

    def test_current_watch_build_configuration(self):
        self.assertEqual([], compatibility_violations(self.original))

    def test_application_id_change_is_detected(self):
        self.assertTrue(any("applicationId" in e for e in self.changed(
            'applicationId = "nl.zennay.raiseai"', 'applicationId = "com.example.demo"')))

    def test_namespace_change_is_detected(self):
        self.assertTrue(any("namespace" in e for e in self.changed(
            'namespace = "nl.zennay.raiseai"', 'namespace = "com.example.demo"')))

    def test_lower_compile_sdk_is_detected(self):
        self.assertTrue(any("compileSdk" in e for e in self.changed(
            "compileSdk = 35", "compileSdk = 34")))

    def test_min_sdk_drift_is_detected(self):
        self.assertTrue(any("minSdk" in e for e in self.changed(
            "minSdk = 30", "minSdk = 31")))

    def test_target_sdk_drift_is_detected(self):
        self.assertTrue(any("targetSdk" in e for e in self.changed(
            "targetSdk = 35", "targetSdk = 34")))

    def test_duplicate_assignment_is_detected(self):
        self.assertTrue(any("minSdk" in e for e in self.changed(
            "minSdk = 30", "minSdk = 30\n        minSdk = 30")))

    def test_alternate_watch_abi_is_detected(self):
        self.assertTrue(any("ABI filter" in e for e in self.changed(
            'abiFilters += "armeabi-v7a"', 'abiFilters += "arm64-v8a"')))

    def test_extra_watch_abi_is_detected(self):
        self.assertTrue(any("ABI filter" in e for e in self.changed(
            'abiFilters += "armeabi-v7a"',
            'abiFilters += "armeabi-v7a"\n            abiFilters += "arm64-v8a"')))

    def test_replacing_abi_filter_with_set_is_detected(self):
        self.assertTrue(any("ABI filter" in e for e in self.changed(
            'abiFilters += "armeabi-v7a"', 'abiFilters.addAll(listOf("armeabi-v7a"))')))

    def test_disabling_build_config_generation_is_detected(self):
        self.assertTrue(any("buildConfig generation" in e for e in self.changed(
            "buildConfig = true", "buildConfig = false")))

    def test_removing_build_provenance_is_detected(self):
        self.assertTrue(any("source revision" in e for e in self.changed(
            'buildConfigField("String", "SOURCE_REVISION", "\\\"$sourceRevision\\\"")',
            '// buildConfigField removed')))

    def test_disabling_post_assemble_abi_verification_is_detected(self):
        self.assertTrue(any("after assembleDebug" in e for e in self.changed(
            'finalizedBy("verifyWatchAbi")', '// disabled verifyWatchAbi')))

    def test_wrong_abi_verifier_expectation_is_detected(self):
        self.assertTrue(any("verifier must expect" in e for e in self.changed(
            'val expected = setOf("armeabi-v7a")',
            'val expected = setOf("arm64-v8a")')))

    def test_abi_verifier_comparison_removal_is_detected(self):
        self.assertTrue(any("compares exact" in e for e in self.changed(
            "check(abis == expected) {", "check(abis.isNotEmpty()) {")))

    def test_release_version_can_change_independently(self):
        # Version metadata is checked elsewhere. It must not falsely trip this
        # compatibility contract during a legitimate reviewed version bump.
        self.assertEqual([], self.changed(
            'versionName = "1.5.3"', 'versionName = "1.5.4"'))

    def test_documentation_comment_does_not_change_abi_policy(self):
        self.assertEqual([], compatibility_violations(
            self.original + '\n// abiFilters += "arm64-v8a" is intentionally not enabled\n'))


if __name__ == "__main__":
    unittest.main()
