#!/usr/bin/env python3
"""Fail-closed, dependency-free source manifest privacy contract for Raise AI.

Run: python3 -m unittest discover -s tests -p 'test_watch_manifest_privacy.py'
This is source-level coverage, NOT physical Watch acceptance or merged APK proof.
"""
from pathlib import Path
import unittest
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "app/src/main/AndroidManifest.xml"
ANDROID = "{http://schemas.android.com/apk/res/android}"
PRIVATE_COMPONENTS = {
    ".AssistantProxyActivity",
    ".NativeVoiceActivity",
    ".ChatGptActivity",
    ".ChatGptProxyActivity",
    ".GestureMonitorService",
}
FORBIDDEN_PERMISSIONS = {
    "android.permission.READ_SMS",
    "android.permission.SEND_SMS",
    "android.permission.READ_CONTACTS",
    "android.permission.READ_CALL_LOG",
    "android.permission.QUERY_ALL_PACKAGES",
    "android.permission.MANAGE_EXTERNAL_STORAGE",
    "android.permission.BIND_ACCESSIBILITY_SERVICE",
}


def violations(data: bytes) -> list[str]:
    try:
        root = ET.fromstring(data)
    except ET.ParseError as exc:
        return [f"unparseable manifest: {exc}"]
    errors = []
    if root.tag != "manifest":
        errors.append("expected manifest root")
    application_nodes = root.findall("application")
    if len(application_nodes) != 1:
        return errors + ["expected exactly one application"]
    app = application_nodes[0]
    for attribute in ("usesCleartextTraffic", "debuggable", "testOnly"):
        if app.get(ANDROID + attribute) == "true":
            errors.append(f"application must not set {attribute}=true")
    permissions = [p.get(ANDROID + "name") for p in root.findall("uses-permission")]
    if len(permissions) != len(set(permissions)):
        errors.append("duplicate permission declaration")
    for permission in permissions:
        if not permission:
            errors.append("unnamed permission")
        elif permission in FORBIDDEN_PERMISSIONS:
            errors.append(f"unexpected sensitive permission: {permission}")
    components = app.findall("activity") + app.findall("service")
    names = [component.get(ANDROID + "name") for component in components]
    for name in PRIVATE_COMPONENTS:
        matches = [component for component in components if component.get(ANDROID + "name") == name]
        if len(matches) != 1 or matches[0].get(ANDROID + "exported") != "false":
            errors.append(f"{name} must exist exactly once and not be exported")
    if len(names) != len(set(names)):
        errors.append("duplicate activity/service name")
    return errors


class WatchManifestPrivacyContract(unittest.TestCase):
    def test_repository_manifest(self):
        self.assertEqual([], violations(MANIFEST.read_bytes()))

    def test_exported_microphone_activity_fails(self):
        manifest = MANIFEST.read_bytes().replace(
            b'android:name=".NativeVoiceActivity"\n            android:excludeFromRecents="true"\n            android:exported="false"',
            b'android:name=".NativeVoiceActivity"\n            android:excludeFromRecents="true"\n            android:exported="true"',
        )
        self.assertIn(".NativeVoiceActivity must exist exactly once and not be exported", violations(manifest))

    def test_added_sensitive_permission_fails(self):
        manifest = MANIFEST.read_bytes().replace(
            b"<queries>", b'<uses-permission android:name="android.permission.READ_SMS" />\n    <queries>',
        )
        self.assertTrue(any("READ_SMS" in item for item in violations(manifest)))

    def test_cleartext_flag_fails(self):
        manifest = MANIFEST.read_bytes().replace(
            b"<application", b'<application android:usesCleartextTraffic="true"', 1
        )
        self.assertIn("application must not set usesCleartextTraffic=true", violations(manifest))

    def test_malformed_xml_fails(self):
        self.assertTrue(violations(b"<manifest"))


if __name__ == "__main__":
    unittest.main()
