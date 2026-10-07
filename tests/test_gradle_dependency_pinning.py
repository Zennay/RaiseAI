from pathlib import Path
import re
import unittest
from urllib.parse import urlsplit


ROOT = Path(__file__).resolve().parents[1]
ROOT_BUILD = ROOT / "build.gradle.kts"
APP_BUILD = ROOT / "app" / "build.gradle.kts"
SETTINGS = ROOT / "settings.gradle.kts"

DYNAMIC_VERSION_MARKERS = ("+", "latest.", "snapshot")


class GradleDependencyPinningTests(unittest.TestCase):
    def setUp(self):
        self.root_build = ROOT_BUILD.read_text(encoding="utf-8")
        self.app_build = APP_BUILD.read_text(encoding="utf-8")
        self.settings = SETTINGS.read_text(encoding="utf-8")

    def test_android_plugin_version_is_literal_and_non_dynamic(self):
        matches = re.findall(
            r'id\("com[.]android[.]application"\)\s+version\s+"([^"]+)"\s+apply false',
            self.root_build,
        )
        self.assertEqual(len(matches), 1)
        version = matches[0].strip()
        self.assertRegex(version, r"^[0-9]+(?:[.][0-9A-Za-z-]+)+$")
        self._assert_non_dynamic(version, "Android Gradle plugin")

    def test_all_declared_library_versions_are_literal_and_non_dynamic(self):
        coordinates = re.findall(
            r'(?m)^\s*(?:implementation|api|testImplementation|androidTestImplementation|debugImplementation|releaseImplementation)\("([^"]+)"\)',
            self.app_build,
        )
        self.assertTrue(coordinates, "app must retain at least one declared dependency")

        for coordinate in coordinates:
            with self.subTest(coordinate=coordinate):
                self.assertNotIn("$", coordinate, "dependency coordinates must not interpolate versions")
                parts = coordinate.rsplit(":", 1)
                self.assertEqual(
                    len(parts),
                    2,
                    f"dependency must include an explicit version: {coordinate}",
                )
                version = parts[1].strip()
                self.assertTrue(version, f"dependency version must not be empty: {coordinate}")
                self._assert_non_dynamic(version, coordinate)

    def test_dependency_repositories_are_reproducible(self):
        lowered = self.settings.lower()
        for forbidden in ("mavenlocal(", "jcenter(", "flatdir"):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(
                    forbidden,
                    lowered,
                    f"non-reproducible repository source is forbidden: {forbidden}",
                )

        self.assertIn(
            "repositoriesMode.set(RepositoriesMode.FAIL_ON_PROJECT_REPOS)",
            self.settings,
        )

        custom_urls = re.findall(r'maven\("([^"]+)"\)', self.settings)
        for raw_url in custom_urls:
            with self.subTest(url=raw_url):
                parsed = urlsplit(raw_url)
                self.assertEqual(parsed.scheme.lower(), "https")
                self.assertTrue(parsed.hostname)
                self.assertIsNone(parsed.username)
                self.assertIsNone(parsed.password)
                self.assertFalse(parsed.query)
                self.assertFalse(parsed.fragment)

    def test_mozilla_repository_is_scoped_to_geckoview_only(self):
        self.assertEqual(
            self.settings.count('maven("https://maven.mozilla.org/maven2/")'),
            1,
            "Mozilla Maven repository must have one canonical declaration",
        )
        scoped = re.search(
            r'(?ms)maven\("https://maven[.]mozilla[.]org/maven2/"\)\s*\{'
            r'\s*content\s*\{\s*includeGroup\("org[.]mozilla[.]geckoview"\)'
            r'\s*\}\s*\}',
            self.settings,
        )
        self.assertIsNotNone(
            scoped,
            "Mozilla Maven must be content-filtered to org.mozilla.geckoview",
        )
        self.assertEqual(
            self.settings.count('includeGroup("org.mozilla.geckoview")'),
            1,
            "GeckoView group filter must be explicit and unique",
        )

    def test_build_scripts_do_not_use_dynamic_dependency_helpers(self):
        combined = self.root_build + "\n" + self.app_build + "\n" + self.settings
        for forbidden in (
            "changing = true",
            "isChanging = true",
            "cacheChangingModulesFor",
            "cacheDynamicVersionsFor",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, combined)

    def _assert_non_dynamic(self, version: str, label: str):
        lowered = version.lower()
        for marker in DYNAMIC_VERSION_MARKERS:
            with self.subTest(label=label, marker=marker):
                self.assertNotIn(
                    marker,
                    lowered,
                    f"{label} must use an immutable dependency version, got {version}",
                )


if __name__ == "__main__":
    unittest.main()
