from pathlib import Path
import re
import unittest
from urllib.parse import urlsplit


ROOT = Path(__file__).resolve().parents[1]
ROOT_BUILD = ROOT / "build.gradle.kts"
APP_BUILD = ROOT / "app" / "build.gradle.kts"
SETTINGS = ROOT / "settings.gradle.kts"

DYNAMIC_VERSION_MARKERS = ("+", "latest.", "snapshot")
CANONICAL_DEPENDENCY_DECLARATION = re.compile(
    r'^\s*[A-Za-z_][A-Za-z0-9_]*\s*\(\s*"'
    r'([A-Za-z0-9_.-]+:[A-Za-z0-9_.-]+:[^"\n]+)"'
    r'\s*\)\s*$'
)


def literal_custom_maven_urls(settings_text: str) -> list[str]:
    return re.findall(r'maven\("([^"]+)"\)', settings_text)


def dynamic_version_markers(version: str) -> list[str]:
    lowered = version.lower()
    markers = [
        marker
        for marker in DYNAMIC_VERSION_MARKERS
        if marker in lowered
    ]
    stripped = version.strip()
    if (
        len(stripped) >= 3
        and stripped[0] in "[("
        and stripped[-1] in "])"
        and "," in stripped
    ):
        markers.append("version-range")
    return markers


def dependency_declaration_lines(build_text: str) -> list[str]:
    lines = build_text.splitlines()
    starts = [
        index
        for index, line in enumerate(lines)
        if re.fullmatch(r"\s*dependencies\s*\{\s*", line.split("//", 1)[0])
    ]
    if len(starts) != 1:
        raise ValueError("build script must contain exactly one canonical dependencies block")

    declarations: list[str] = []
    depth = 1
    for line in lines[starts[0] + 1 :]:
        code = line.split("//", 1)[0].strip()
        if not code:
            continue

        depth += code.count("{") - code.count("}")
        if depth == 0:
            return declarations
        if depth != 1:
            raise ValueError(
                "dependencies block must use flat canonical dependency declarations"
            )
        declarations.append(code)

    raise ValueError("dependencies block is not closed")


def canonical_dependency_coordinate(line: str) -> str | None:
    match = CANONICAL_DEPENDENCY_DECLARATION.fullmatch(line)
    return match.group(1) if match else None


def literal_dependency_coordinates(build_text: str) -> list[str]:
    return re.findall(
        r'(?m)^\s*[A-Za-z_][A-Za-z0-9_]*\s*\(\s*"'
        r'([A-Za-z0-9_.-]+:[A-Za-z0-9_.-]+:[^"\n]+)"'
        r'\s*\)\s*(?://.*)?$',
        build_text,
    )


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
        coordinates = literal_dependency_coordinates(self.app_build)
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

    def test_every_dependency_declaration_uses_reviewed_literal_coordinate_form(self):
        declarations = dependency_declaration_lines(self.app_build)
        self.assertTrue(declarations, "dependencies block must not be empty")

        parsed = []
        for declaration in declarations:
            with self.subTest(declaration=declaration):
                coordinate = canonical_dependency_coordinate(declaration)
                self.assertIsNotNone(
                    coordinate,
                    "dependency declarations must use configuration(\"group:artifact:version\") "
                    "so every version remains visible to the pinning contract",
                )
                parsed.append(coordinate)

        self.assertEqual(
            parsed,
            literal_dependency_coordinates(self.app_build),
            "canonical declaration scan and coordinate discovery must cover the same surface",
        )

    def test_unsupported_dependency_declaration_forms_fail_closed(self):
        unsupported = (
            'implementation("example.group:artifact")',
            'implementation(platform("example.group:bom:1.0.0"))',
            'add("implementation", "example.group:artifact:1.0.0")',
            'implementation(group = "example.group", name = "artifact", version = "1.0.0")',
        )
        for declaration in unsupported:
            with self.subTest(declaration=declaration):
                self.assertIsNone(canonical_dependency_coordinate(declaration))

        with self.assertRaisesRegex(ValueError, "flat canonical"):
            dependency_declaration_lines(
                "dependencies {\n"
                "    constraints {\n"
                '        implementation("example.group:artifact:1.0.0")\n'
                "    }\n"
                "}\n"
            )

    def test_dependency_coordinate_discovery_is_configuration_name_agnostic(self):
        fixture = """
dependencies {
    compileOnly("example.compile:artifact:1.0.0")
    runtimeOnly("example.runtime:artifact:2.0.0")
    testRuntimeOnly("example.test:artifact:3.0.0")
    androidTestRuntimeOnly("example.androidtest:artifact:+")
}
"""
        self.assertEqual(
            literal_dependency_coordinates(fixture),
            [
                "example.compile:artifact:1.0.0",
                "example.runtime:artifact:2.0.0",
                "example.test:artifact:3.0.0",
                "example.androidtest:artifact:+",
            ],
        )
        with self.assertRaises(AssertionError):
            self._assert_non_dynamic(
                literal_dependency_coordinates(fixture)[-1],
                "androidTestRuntimeOnly fixture",
            )

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

        custom_urls = literal_custom_maven_urls(self.settings)
        for raw_url in custom_urls:
            with self.subTest(url=raw_url):
                parsed = urlsplit(raw_url)
                self.assertEqual(parsed.scheme.lower(), "https")
                self.assertTrue(parsed.hostname)
                self.assertIsNone(parsed.username)
                self.assertIsNone(parsed.password)
                self.assertFalse(parsed.query)
                self.assertFalse(parsed.fragment)

    def test_repository_sources_are_explicitly_allowlisted(self):
        custom_urls = literal_custom_maven_urls(self.settings)
        self.assertEqual(
            custom_urls,
            ["https://maven.mozilla.org/maven2/"],
            "custom Maven repositories must stay on the reviewed Mozilla-only allowlist",
        )

        expected_builtin_counts = {
            "google()": 2,
            "mavenCentral()": 2,
            "gradlePluginPortal()": 1,
        }
        for declaration, expected_count in expected_builtin_counts.items():
            with self.subTest(declaration=declaration):
                self.assertEqual(
                    self.settings.count(declaration),
                    expected_count,
                    f"unexpected Gradle repository declaration drift: {declaration}",
                )

        for forbidden_form in (
            r"(?m)^\s*maven\s*\{",
            r"\bmaven\s*\(\s*url\s*=",
            r"\bmaven\s*\(\s*uri\s*\(",
            r"(?m)^\s*ivy\s*(?:\(|\{)",
        ):
            with self.subTest(forbidden_form=forbidden_form):
                self.assertNotRegex(
                    self.settings,
                    forbidden_form,
                    "repository declarations must use the reviewed canonical forms",
                )

    def test_custom_maven_repository_parser_covers_literal_urls(self):
        fixture = """
repositories {
    maven("https://repo.example.test/releases/")
    maven("http://repo.example.test/insecure/")
}
"""
        self.assertEqual(
            literal_custom_maven_urls(fixture),
            [
                "https://repo.example.test/releases/",
                "http://repo.example.test/insecure/",
            ],
        )

    def test_rejects_gradle_maven_version_ranges(self):
        for version in (
            "[1.0,2.0)",
            "(,1.5]",
            "[1.0,)",
            "(1.0,2.0]",
        ):
            with self.subTest(version=version):
                with self.assertRaises(AssertionError):
                    self._assert_non_dynamic(version, "range fixture")

        for version in ("1.2.3", "2026.10.0-alpha1"):
            with self.subTest(version=version):
                self._assert_non_dynamic(version, "fixed fixture")

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
        markers = dynamic_version_markers(version)
        self.assertEqual(
            markers,
            [],
            f"{label} must use an immutable dependency version, got {version}; "
            f"dynamic markers={markers}",
        )


if __name__ == "__main__":
    unittest.main()
