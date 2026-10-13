"""Prevent JUnit Jupiter conditional annotations silently excluding Watch tests.

Kotlin @Ignore/@Disabled and runtime JUnit assumptions already have source
guards; Jupiter's @EnabledOnOs and @DisabledIfEnvironmentVariable families
are a separate route to reporting tests as skipped without executing them.
This is static source protection, not JVM/physical Watch execution evidence.
"""
from __future__ import annotations

from pathlib import Path
import re
import unittest

if __package__:
    from .test_kotlin_junit_disable_contract import kotlin_code_only, kotlin_test_paths
else:
    from test_kotlin_junit_disable_contract import kotlin_code_only, kotlin_test_paths


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = "org.junit.jupiter.api.condition"
CONDITIONS = frozenset({
    "EnabledOnOs", "DisabledOnOs",
    "EnabledOnJre", "DisabledOnJre",
    "EnabledForJreRange", "DisabledForJreRange",
    "EnabledIfEnvironmentVariable", "DisabledIfEnvironmentVariable",
    "EnabledIfEnvironmentVariables", "DisabledIfEnvironmentVariables",
    "EnabledIfSystemProperty", "DisabledIfSystemProperty",
    "EnabledIfSystemProperties", "DisabledIfSystemProperties",
    "EnabledIf", "DisabledIf",
    "EnabledInNativeImage", "DisabledInNativeImage",
})
IMPORT = re.compile(
    r"(?m)^[ \t]*import[ \t]+"
    r"org\.junit\.jupiter\.api\.condition\."
    r"(\*|[A-Za-z_][A-Za-z_0-9]*)"
    r"(?:[ \t]+as[ \t]+([A-Za-z_][A-Za-z_0-9]*))?[ \t]*$"
)
TYPEALIAS = re.compile(
    r"(?m)^[ \t]*(?:public[ \t]+|private[ \t]+|internal[ \t]+)?"
    r"typealias[ \t]+([A-Za-z_][A-Za-z_0-9]*)[ \t]*="
    r"[ \t]*([A-Za-z_][A-Za-z_0-9]*(?:\.[A-Za-z_][A-Za-z_0-9]*)*)[ \t]*$"
)
ANNOTATION = re.compile(
    r"@(?:[A-Za-z_][A-Za-z_0-9]*:)?"
    r"([A-Za-z_][A-Za-z_0-9]*(?:\.[A-Za-z_][A-Za-z_0-9]*)*)"
)


def conditional_junit_annotations(source: str) -> list[tuple[int, str]]:
    """Return active imported/qualified test-selection annotations.

    An alias imported from another package is not JUnit. Kotlin typealias
    chains can disguise selection conditions and are resolved to fixpoint.
    """
    code = kotlin_code_only(source)
    resolved = {f"{PACKAGE}.{name}" for name in CONDITIONS}
    for match in IMPORT.finditer(code):
        name, alias = match.groups()
        if name == "*":
            resolved.update(CONDITIONS)
        elif name in CONDITIONS:
            resolved.add(alias or name)

    aliases = TYPEALIAS.findall(code)
    for _ in range(len(aliases) + 1):
        changed = False
        for name, target in aliases:
            if target in resolved and name not in resolved:
                resolved.add(name)
                changed = True
        if not changed:
            break

    matches = []
    for match in ANNOTATION.finditer(code):
        name = match.group(1)
        if name in resolved:
            line = code.count("\n", 0, match.start()) + 1
            matches.append((line, name))
    return matches


class KotlinJupiterConditionalAnnotationsContract(unittest.TestCase):
    def test_real_kotlin_suites_do_not_use_conditional_exclusions(self):
        paths = kotlin_test_paths()
        self.assertTrue(paths, "Kotlin test tree must contain source")
        violations = []
        for path in paths:
            self.assertTrue(path.is_file() and not path.is_symlink())
            for line, name in conditional_junit_annotations(path.read_text(encoding="utf-8")):
                violations.append(f"{path.relative_to(ROOT)}:{line}: @{name}")
        self.assertEqual([], violations, "\n".join(violations))

    def test_qualified_os_and_jre_conditions_are_rejected(self):
        source = (
            "@org.junit.jupiter.api.condition.EnabledOnOs(OS.LINUX)\n"
            "class Selective\n"
            "@org.junit.jupiter.api.condition.DisabledForJreRange(min = JRE.JAVA_17)\n"
            "fun conditional() = Unit\n"
        )
        self.assertEqual(
            [(1, "org.junit.jupiter.api.condition.EnabledOnOs"),
             (3, "org.junit.jupiter.api.condition.DisabledForJreRange")],
            conditional_junit_annotations(source),
        )

    def test_environment_conditions_are_rejected(self):
        source = (
            "import org.junit.jupiter.api.condition.DisabledIfEnvironmentVariable\n"
            '@DisabledIfEnvironmentVariable(named = "CI", matches = "true")\n'
            "class Skipped\n"
        )
        self.assertEqual(
            [(2, "DisabledIfEnvironmentVariable")],
            conditional_junit_annotations(source),
        )

    def test_system_property_condition_is_rejected(self):
        source = (
            "import org.junit.jupiter.api.condition.EnabledIfSystemProperty\n"
            "@EnabledIfSystemProperty(named = \"os.name\", matches = \"Linux\")\n"
            "fun onlyOnLinux() = Unit\n"
        )
        self.assertEqual(
            [(2, "EnabledIfSystemProperty")],
            conditional_junit_annotations(source),
        )

    def test_native_image_and_expression_conditions_are_rejected(self):
        source = (
            "import org.junit.jupiter.api.condition.EnabledInNativeImage\n"
            "import org.junit.jupiter.api.condition.DisabledIf\n"
            "@EnabledInNativeImage\n"
            "class NativeOnly\n"
            '@DisabledIf("methodName")\n'
            "fun conditional() = Unit\n"
        )
        self.assertEqual(
            [(3, "EnabledInNativeImage"), (5, "DisabledIf")],
            conditional_junit_annotations(source),
        )

    def test_import_alias_condition_is_rejected(self):
        source = (
            "import org.junit.jupiter.api.condition.DisabledOnOs as DropOnOs\n"
            "@DropOnOs(OS.LINUX)\n"
            "class Conditional\n"
        )
        self.assertEqual([(2, "DropOnOs")], conditional_junit_annotations(source))

    def test_wildcard_import_resolves_known_junit_conditions(self):
        source = (
            "import org.junit.jupiter.api.condition.*\n"
            "@EnabledOnJre(JRE.JAVA_21)\n"
            "@DisabledIfSystemProperties(value = [])\n"
            "class Conditional\n"
        )
        self.assertEqual(
            [(2, "EnabledOnJre"), (3, "DisabledIfSystemProperties")],
            conditional_junit_annotations(source),
        )

    def test_reverse_declared_transitive_typealias_is_rejected(self):
        declarations = [
            f"typealias Link{index} = "
            + (f"{PACKAGE}.DisabledOnOs" if index == 0 else f"Link{index - 1}")
            for index in range(70)
        ]
        source = "\n".join(reversed(declarations)) + "\n@Link69\nfun skip() = Unit\n"
        self.assertEqual([(71, "Link69")], conditional_junit_annotations(source))

    def test_use_site_target_condition_is_rejected(self):
        self.assertEqual(
            [(2, "EnabledIfEnvironmentVariables")],
            conditional_junit_annotations(
                "import org.junit.jupiter.api.condition.EnabledIfEnvironmentVariables\n"
                "@get:EnabledIfEnvironmentVariables(value = [])\nval x = 2\n"
            ),
        )

    def test_similarly_named_other_libraries_do_not_count(self):
        self.assertEqual(
            [],
            conditional_junit_annotations(
                "import my.project.EnabledOnOs\n"
                "import other.package.DisabledIf as Conditional\n"
                "@EnabledOnOs\n@Conditional\n"
                "@other.package.DisabledOnOs\n"
                "class NotJunit\n"
            ),
        )

    def test_raw_and_nested_comments_cannot_forge_a_condition(self):
        self.assertEqual(
            [],
            conditional_junit_annotations(
                "import org.junit.jupiter.api.condition.DisabledOnOs\n"
                "// @DisabledOnOs\n"
                "/* @DisabledOnOs /* @DisabledOnOs */ */\n"
                'val sample = """@DisabledOnOs""" \n'
                'val quoted = "@DisabledOnOs"\n'
            ),
        )

    def test_an_unimported_short_name_is_not_attributed_to_junit(self):
        self.assertEqual(
            [],
            conditional_junit_annotations(
                "@DisabledOnOs\nclass CustomAnnotationInSamePackage\n"
            ),
        )

    def test_invalid_literals_and_block_comments_fail_closed(self):
        for source in ('val bad = """incomplete', "/* open"):
            with self.subTest(source=source):
                with self.assertRaises(ValueError):
                    conditional_junit_annotations(source)

    def test_normal_junit_test_annotation_is_accepted(self):
        self.assertEqual(
            [],
            conditional_junit_annotations(
                "import org.junit.Test\n"
                "@Test fun valid() = Unit\n"
                "@org.junit.jupiter.api.Test fun alsoValid() = Unit\n"
            ),
        )


if __name__ == "__main__":
    unittest.main()
