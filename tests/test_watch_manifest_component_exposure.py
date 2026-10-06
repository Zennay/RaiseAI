import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

ANDROID = "{http://schemas.android.com/apk/res/android}"
MANIFEST = Path(__file__).resolve().parents[1] / "app" / "src" / "main" / "AndroidManifest.xml"


def attr(node, name):
    return node.get(ANDROID + name)


class WatchManifestComponentExposureTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = ET.parse(MANIFEST).getroot()
        cls.application = cls.root.find("application")
        if cls.application is None:
            raise AssertionError("AndroidManifest.xml has no <application>")

    def components(self, kind):
        return self.application.findall(kind)

    def by_name(self, kind, name):
        matches = [node for node in self.components(kind) if attr(node, "name") == name]
        self.assertEqual(len(matches), 1, f"expected exactly one {kind} {name}")
        return matches[0]

    def test_only_launcher_activity_is_exported(self):
        exported = {
            attr(node, "name")
            for node in self.components("activity")
            if attr(node, "exported") == "true"
        }
        self.assertEqual(exported, {".MainActivity"})

        launcher = self.by_name("activity", ".MainActivity")
        actions = {
            attr(action, "name")
            for intent_filter in launcher.findall("intent-filter")
            for action in intent_filter.findall("action")
        }
        categories = {
            attr(category, "name")
            for intent_filter in launcher.findall("intent-filter")
            for category in intent_filter.findall("category")
        }
        self.assertIn("android.intent.action.MAIN", actions)
        self.assertIn("android.intent.category.LAUNCHER", categories)

    def test_internal_activities_are_explicitly_not_exported(self):
        for name in (
            ".AssistantProxyActivity",
            ".NativeVoiceActivity",
            ".ChatGptActivity",
            ".ChatGptProxyActivity",
        ):
            self.assertEqual(attr(self.by_name("activity", name), "exported"), "false", name)

    def test_no_service_or_provider_is_exported(self):
        for kind in ("service", "provider"):
            exported = [
                attr(node, "name")
                for node in self.components(kind)
                if attr(node, "exported") == "true"
            ]
            self.assertEqual(exported, [], f"unexpected exported {kind}: {exported}")

    def test_gesture_monitor_service_stays_internal_special_use(self):
        service = self.by_name("service", ".GestureMonitorService")
        self.assertEqual(attr(service, "exported"), "false")
        self.assertEqual(attr(service, "foregroundServiceType"), "specialUse")

    def test_boot_receiver_has_only_system_recovery_actions(self):
        receiver = self.by_name("receiver", ".BootReceiver")
        actions = {
            attr(action, "name")
            for intent_filter in receiver.findall("intent-filter")
            for action in intent_filter.findall("action")
        }
        self.assertEqual(
            actions,
            {
                "android.intent.action.BOOT_COMPLETED",
                "android.intent.action.MY_PACKAGE_REPLACED",
            },
        )

    def test_manifest_does_not_opt_into_cleartext(self):
        self.assertNotEqual(attr(self.application, "usesCleartextTraffic"), "true")


if __name__ == "__main__":
    unittest.main()
