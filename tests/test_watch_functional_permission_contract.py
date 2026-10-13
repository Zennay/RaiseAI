#!/usr/bin/env python3
"""Source-only regression for Raise AI's indispensable Watch permissions.

The Android manifest grants no runtime permissions by itself; this contract
protects declarations needed by voice, networking, boot restore and foreground
gesture monitoring. It is not physical Galaxy Watch 7 evidence.
"""
from pathlib import Path
import unittest
import xml.etree.ElementTree as ET

MANIFEST = Path(__file__).resolve().parents[1] / "app/src/main/AndroidManifest.xml"
ANDROID = "{http://schemas.android.com/apk/res/android}"
CORE_PERMISSIONS = frozenset({
    "android.permission.INTERNET",
    "android.permission.RECORD_AUDIO",
    "android.permission.FOREGROUND_SERVICE",
    "android.permission.FOREGROUND_SERVICE_SPECIAL_USE",
    "android.permission.RECEIVE_BOOT_COMPLETED",
})
ALIASES = frozenset({"uses-permission-sdk-23", "uses-permission-sdk-m"})


def permission_gate_violations(payload: bytes) -> list[str]:
    try:
        root = ET.fromstring(payload)
    except ET.ParseError as exc:
        return [f"invalid manifest XML: {exc}"]
    if root.tag != "manifest":
        return ["expected manifest root"]

    errors: list[str] = []
    direct = root.findall("uses-permission")
    all_nodes = [
        node for node in root.iter()
        if node.tag == "uses-permission" or node.tag in ALIASES
    ]
    for node in all_nodes:
        if node not in direct:
            errors.append(f"permission declaration outside canonical root: {node.tag}")

    counts: dict[str, int] = {name: 0 for name in CORE_PERMISSIONS}
    for node in all_nodes:
        name = node.get(ANDROID + "name")
        if name not in CORE_PERMISSIONS:
            continue
        counts[name] += 1
        if node.tag != "uses-permission":
            errors.append(f"{name}: use canonical uses-permission element")
        if node.get(ANDROID + "maxSdkVersion") is not None:
            errors.append(f"{name}: maxSdkVersion must not gate core permission")
        if node.get(ANDROID + "usesPermissionFlags") is not None:
            errors.append(f"{name}: usesPermissionFlags must not alter core permission")
    for name in sorted(CORE_PERMISSIONS):
        if counts[name] != 1:
            errors.append(f"{name}: expected exactly one core permission, found {counts[name]}")
    return errors


class WatchFunctionalPermissionContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.original = MANIFEST.read_bytes()

    def changed(self, mutate):
        root = ET.fromstring(self.original)
        mutate(root)
        return permission_gate_violations(ET.tostring(root))

    @staticmethod
    def permission(root, name):
        return next(
            node for node in root.findall("uses-permission")
            if node.get(ANDROID + "name") == name
        )

    def test_repository_manifest(self):
        self.assertEqual([], permission_gate_violations(self.original))

    def test_missing_record_audio_detected(self):
        def change(root):
            root.remove(self.permission(root, "android.permission.RECORD_AUDIO"))
        self.assertTrue(any("RECORD_AUDIO" in error for error in self.changed(change)))

    def test_missing_internet_detected(self):
        def change(root):
            root.remove(self.permission(root, "android.permission.INTERNET"))
        self.assertTrue(any("INTERNET" in error for error in self.changed(change)))

    def test_missing_boot_permission_detected(self):
        def change(root):
            root.remove(self.permission(root, "android.permission.RECEIVE_BOOT_COMPLETED"))
        self.assertTrue(any("RECEIVE_BOOT_COMPLETED" in error for error in self.changed(change)))

    def test_missing_service_permission_detected(self):
        def change(root):
            root.remove(self.permission(root, "android.permission.FOREGROUND_SERVICE"))
        self.assertTrue(any("FOREGROUND_SERVICE:" in error for error in self.changed(change)))

    def test_missing_special_use_service_permission_detected(self):
        def change(root):
            root.remove(self.permission(root, "android.permission.FOREGROUND_SERVICE_SPECIAL_USE"))
        self.assertTrue(any("FOREGROUND_SERVICE_SPECIAL_USE" in error for error in self.changed(change)))

    def test_duplicate_core_permission_detected(self):
        def change(root):
            ET.SubElement(root, "uses-permission", {
                ANDROID + "name": "android.permission.RECORD_AUDIO",
            })
        self.assertTrue(any("found 2" in error for error in self.changed(change)))

    def test_max_sdk_version_on_core_permission_detected(self):
        def change(root):
            self.permission(root, "android.permission.RECORD_AUDIO").set(
                ANDROID + "maxSdkVersion", "32"
            )
        self.assertTrue(any("maxSdkVersion" in error for error in self.changed(change)))

    def test_permission_flags_on_core_permission_detected(self):
        def change(root):
            self.permission(root, "android.permission.RECORD_AUDIO").set(
                ANDROID + "usesPermissionFlags", "neverForLocation"
            )
        self.assertTrue(any("usesPermissionFlags" in error for error in self.changed(change)))

    def test_noncanonical_sdk_permission_alias_detected(self):
        def change(root):
            old = self.permission(root, "android.permission.RECORD_AUDIO")
            root.remove(old)
            ET.SubElement(root, "uses-permission-sdk-23", {
                ANDROID + "name": "android.permission.RECORD_AUDIO",
            })
        problems = self.changed(change)
        self.assertTrue(any("canonical" in error for error in problems))

    def test_nested_permission_declaration_detected(self):
        def change(root):
            old = self.permission(root, "android.permission.RECORD_AUDIO")
            root.remove(old)
            app = root.find("application")
            assert app is not None
            app.append(old)
        self.assertTrue(any("outside canonical root" in error for error in self.changed(change)))

    def test_additional_unrelated_optional_permission_remains_allowed(self):
        def change(root):
            ET.SubElement(root, "uses-permission", {
                ANDROID + "name": "android.permission.VIBRATE",
            })
        self.assertEqual([], self.changed(change))

    def test_wrong_root_detected(self):
        self.assertIn("expected manifest root", permission_gate_violations(b"<application/>"))

    def test_invalid_xml_detected(self):
        self.assertTrue(permission_gate_violations(b"<manifest"))


if __name__ == "__main__":
    unittest.main()
