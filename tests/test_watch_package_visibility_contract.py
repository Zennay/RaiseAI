#!/usr/bin/env python3
"""Fail-closed source contract for Android 11+ Watch package visibility.

Android <queries> is a privacy surface independent of QUERY_ALL_PACKAGES.
This module audits source XML only; it does not prove merged APK or device
behaviour. Any legitimate newly queried app requires explicit policy review.
"""
from pathlib import Path
import unittest
import xml.etree.ElementTree as ET

MANIFEST = Path(__file__).resolve().parents[1] / "app/src/main/AndroidManifest.xml"
ANDROID = "{http://schemas.android.com/apk/res/android}"
ALLOWED_PACKAGES = frozenset({
    "com.google.android.wearable.assistant",
    "com.google.android.apps.chromecast.app",
    "com.sec.android.app.sbrowser",
})
ALLOWED_ACTION = "android.intent.action.TTS_SERVICE"


def visibility_violations(payload: bytes) -> list[str]:
    try:
        root = ET.fromstring(payload)
    except ET.ParseError as exc:
        return [f"malformed AndroidManifest.xml: {exc}"]
    if root.tag != "manifest":
        return ["expected manifest root"]

    queries = root.findall("queries")
    errors: list[str] = []
    if len(queries) != 1:
        errors.append(f"expected exactly one root queries section, found {len(queries)}")

    # A nested second section is never legitimate package-visibility policy.
    for parent in root.iter():
        if parent is root:
            continue
        if any(child.tag == "queries" for child in parent):
            errors.append("nested queries section is forbidden")

    if len(queries) != 1:
        return errors

    section = queries[0]
    if section.attrib:
        errors.append("queries section must not have attributes")
    names: list[str] = []
    intents = []
    for child in section:
        if child.tag == "package":
            name = child.get(ANDROID + "name")
            if set(child.attrib) != {ANDROID + "name"}:
                errors.append("package query requires only android:name")
            if list(child):
                errors.append("package query must not have nested elements")
            if not name or not name.strip() or name != name.strip():
                errors.append("package query name missing or malformed")
            else:
                names.append(name)
                if name not in ALLOWED_PACKAGES:
                    errors.append(f"unexpected package visibility: {name}")
        elif child.tag == "intent":
            intents.append(child)
        else:
            errors.append(f"unsupported package visibility element: {child.tag}")

    if len(names) != len(set(names)):
        errors.append("duplicate package visibility declaration")
    if set(names) != ALLOWED_PACKAGES:
        errors.append("package visibility allowlist mismatch")
    if len(intents) != 1:
        errors.append(f"expected one TTS visibility intent, found {len(intents)}")
    else:
        intent = intents[0]
        if intent.attrib:
            errors.append("visibility intent attributes are forbidden")
        actions = list(intent)
        if (len(actions) != 1 or actions[0].tag != "action"
                or actions[0].attrib != {ANDROID + "name": ALLOWED_ACTION}
                or list(actions[0])):
            errors.append("only the exact TTS_SERVICE visibility intent is allowed")
    return errors


class WatchPackageVisibilityContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.original = MANIFEST.read_bytes()

    def changed(self, mutate):
        root = ET.fromstring(self.original)
        mutate(root)
        return visibility_violations(ET.tostring(root))

    @staticmethod
    def queries(root):
        element = root.find("queries")
        assert element is not None
        return element

    def test_repository_visibility_is_allowlisted(self):
        self.assertEqual([], visibility_violations(self.original))

    def test_missing_queries_fails(self):
        self.assertTrue(self.changed(lambda root: root.remove(self.queries(root))))

    def test_duplicate_queries_fails(self):
        def edit(root):
            ET.SubElement(root, "queries")
        self.assertTrue(any("exactly one" in s for s in self.changed(edit)))

    def test_nested_queries_fails(self):
        def edit(root):
            ET.SubElement(root.find("application"), "queries")
        self.assertTrue(any("nested queries" in s for s in self.changed(edit)))

    def test_new_package_fails(self):
        def edit(root):
            ET.SubElement(self.queries(root), "package", {
                ANDROID + "name": "com.example.other",
            })
        self.assertTrue(any("unexpected package" in s for s in self.changed(edit)))

    def test_missing_assistant_package_fails(self):
        def edit(root):
            q = self.queries(root)
            q.remove(next(p for p in q.findall("package")
                if p.get(ANDROID + "name") == "com.google.android.wearable.assistant"))
        self.assertTrue(any("allowlist mismatch" in s for s in self.changed(edit)))

    def test_duplicate_package_fails(self):
        def edit(root):
            ET.SubElement(self.queries(root), "package", {
                ANDROID + "name": "com.sec.android.app.sbrowser",
            })
        self.assertTrue(any("duplicate package" in s for s in self.changed(edit)))

    def test_package_has_extra_attributes_fails(self):
        def edit(root):
            self.queries(root).find("package").set(ANDROID + "required", "true")
        self.assertTrue(any("only android:name" in s for s in self.changed(edit)))

    def test_blank_package_name_fails(self):
        def edit(root):
            self.queries(root).find("package").set(ANDROID + "name", " ")
        self.assertTrue(any("missing or malformed" in s for s in self.changed(edit)))

    def test_wildcard_provider_visibility_fails(self):
        def edit(root):
            ET.SubElement(self.queries(root), "provider", {
                ANDROID + "authorities": "*",
            })
        self.assertTrue(any("unsupported package" in s for s in self.changed(edit)))

    def test_second_visibility_intent_fails(self):
        def edit(root):
            ET.SubElement(self.queries(root), "intent")
        self.assertTrue(any("expected one TTS" in s for s in self.changed(edit)))

    def test_broad_view_intent_fails(self):
        def edit(root):
            q = self.queries(root)
            i = q.find("intent")
            i.find("action").set(ANDROID + "name", "android.intent.action.VIEW")
        self.assertTrue(any("exact TTS_SERVICE" in s for s in self.changed(edit)))

    def test_extra_intent_data_fails(self):
        def edit(root):
            ET.SubElement(self.queries(root).find("intent"), "data", {
                ANDROID + "scheme": "https",
            })
        self.assertTrue(any("exact TTS_SERVICE" in s for s in self.changed(edit)))

    def test_unexpected_query_attributes_fail(self):
        def edit(root):
            self.queries(root).set("extension", "hidden")
        self.assertTrue(any("must not have attributes" in s for s in self.changed(edit)))

    def test_package_query_order_is_not_part_of_contract(self):
        def edit(root):
            q = self.queries(root)
            children = list(q)
            q[:] = list(reversed(children))
        self.assertEqual([], self.changed(edit))

    def test_non_manifest_root_fails(self):
        self.assertIn("expected manifest root", visibility_violations(b"<application/>"))

    def test_invalid_xml_fails(self):
        self.assertTrue(visibility_violations(b"<manifest"))


if __name__ == "__main__":
    unittest.main()
