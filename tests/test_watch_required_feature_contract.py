#!/usr/bin/env python3
"""Fail-closed Watch hardware capability manifest contract.

This is a SOURCE contract run by the hosted All Python contracts CI. It does
not prove installability, physical gesture behavior or Galaxy Watch 7 acceptance.
"""
from pathlib import Path
import unittest
import xml.etree.ElementTree as ET

MANIFEST = Path(__file__).resolve().parents[1] / "app/src/main/AndroidManifest.xml"
ANDROID = "{http://schemas.android.com/apk/res/android}"
REQUIRED_FEATURES = frozenset({
    "android.hardware.type.watch",
    "android.hardware.sensor.accelerometer",
})


def feature_contract_violations(manifest: bytes) -> list[str]:
    """Require exact Wear/accelerometer capabilities without accidental filtering."""
    try:
        root = ET.fromstring(manifest)
    except ET.ParseError as exc:
        return [f"malformed Android manifest: {exc}"]
    if root.tag != "manifest":
        return ["expected manifest root"]

    errors: list[str] = []
    direct = root.findall("uses-feature")
    seen: set[str] = set()
    for element in root.iter("uses-feature"):
        if element not in direct:
            errors.append("uses-feature must be a direct manifest child")
    for element in direct:
        name = element.get(ANDROID + "name")
        required = element.get(ANDROID + "required")
        if not name or not name.strip() or name != name.strip():
            errors.append("uses-feature must declare an unambiguous android:name")
            continue
        if name in seen:
            errors.append(f"duplicate uses-feature: {name}")
        seen.add(name)

        # Android defaults missing required= to true; require explicit values
        # to avoid unexpectedly filtering out otherwise supported devices.
        if required not in ("true", "false"):
            errors.append(f"{name}: android:required must be explicit true or false")
        elif name in REQUIRED_FEATURES and required != "true":
            errors.append(f"{name}: required Watch hardware must remain required")
        elif name not in REQUIRED_FEATURES and required != "false":
            errors.append(f"{name}: new hardware features must be optional")
    for name in sorted(REQUIRED_FEATURES - seen):
        errors.append(f"missing required Watch hardware feature: {name}")
    return errors


class WatchRequiredFeatureContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest = MANIFEST.read_bytes()

    def modified(self, edit):
        root = ET.fromstring(self.manifest)
        edit(root)
        return feature_contract_violations(ET.tostring(root))

    @staticmethod
    def feature(root, name):
        return next(
            el for el in root.findall("uses-feature")
            if el.get(ANDROID + "name") == name
        )

    def test_current_manifest_exposes_required_watch_capabilities(self):
        self.assertEqual([], feature_contract_violations(self.manifest))

    def test_removed_watch_feature_fails(self):
        def edit(root):
            root.remove(self.feature(root, "android.hardware.type.watch"))
        self.assertTrue(any("missing required Watch hardware" in s for s in self.modified(edit)))

    def test_removed_accelerometer_feature_fails(self):
        def edit(root):
            root.remove(self.feature(root, "android.hardware.sensor.accelerometer"))
        self.assertTrue(any("missing required Watch hardware" in s for s in self.modified(edit)))

    def test_optional_accelerometer_fails(self):
        def edit(root):
            self.feature(root, "android.hardware.sensor.accelerometer").set(
                ANDROID + "required", "false"
            )
        self.assertTrue(any("must remain required" in s for s in self.modified(edit)))

    def test_missing_required_attribute_fails_even_for_known_hardware(self):
        def edit(root):
            self.feature(root, "android.hardware.type.watch").attrib.pop(
                ANDROID + "required"
            )
        self.assertTrue(any("must be explicit" in s for s in self.modified(edit)))

    def test_duplicate_required_declaration_fails(self):
        def edit(root):
            ET.SubElement(root, "uses-feature", {
                ANDROID + "name": "android.hardware.type.watch",
                ANDROID + "required": "true",
            })
        self.assertTrue(any("duplicate uses-feature" in s for s in self.modified(edit)))

    def test_unexpected_required_camera_fails(self):
        def edit(root):
            ET.SubElement(root, "uses-feature", {
                ANDROID + "name": "android.hardware.camera",
                ANDROID + "required": "true",
            })
        self.assertTrue(any("must be optional" in s for s in self.modified(edit)))

    def test_new_optional_feature_allowed(self):
        def edit(root):
            ET.SubElement(root, "uses-feature", {
                ANDROID + "name": "android.hardware.bluetooth",
                ANDROID + "required": "false",
            })
        self.assertEqual([], self.modified(edit))

    def test_missing_required_value_on_new_feature_fails(self):
        def edit(root):
            ET.SubElement(root, "uses-feature", {
                ANDROID + "name": "android.hardware.camera",
            })
        self.assertTrue(any("must be explicit" in s for s in self.modified(edit)))

    def test_missing_name_fails(self):
        def edit(root):
            ET.SubElement(root, "uses-feature", {ANDROID + "required": "false"})
        self.assertTrue(any("unambiguous android:name" in s for s in self.modified(edit)))

    def test_nested_shadow_feature_fails(self):
        def edit(root):
            application = root.find("application")
            assert application is not None
            ET.SubElement(application, "uses-feature", {
                ANDROID + "name": "android.hardware.camera",
                ANDROID + "required": "false",
            })
        self.assertTrue(any("direct manifest child" in s for s in self.modified(edit)))

    def test_invalid_root_fails(self):
        self.assertIn("expected manifest root", feature_contract_violations(b"<application/>"))

    def test_malformed_xml_fails(self):
        self.assertTrue(feature_contract_violations(b"<manifest"))


if __name__ == "__main__":
    unittest.main()
