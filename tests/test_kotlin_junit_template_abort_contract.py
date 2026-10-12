"""Detect JUnit runtime skips hidden inside *executable* Kotlin string templates.

A Kotlin string literal's text is inert, but expressions inside ${...}
actually execute. The JUnit abort scanner correctly ignores quoted fixtures
and therefore cannot see an Assume call inside an interpolation expression.
This additional contract inspects only executable template expressions.
"""
from __future__ import annotations

from pathlib import Path
import unittest

if __package__:
    from .test_kotlin_junit_runtime_abort_contract import junit_runtime_aborts
    from .test_kotlin_junit_disable_contract import kotlin_test_paths
else:
    from test_kotlin_junit_runtime_abort_contract import junit_runtime_aborts
    from test_kotlin_junit_disable_contract import kotlin_test_paths


ROOT = Path(__file__).resolve().parents[1]


def kotlin_template_expression_spans(source: str) -> list[tuple[int, int]]:
    """Return source ranges inside valid string interpolation expression braces.

    Recognize normal and triple-quoted strings, nested string templates,
    nested brace expressions, escaped dollar signs and nested comments.
    Malformed input fails closed; ordinary quoted fixture text is not code.
    """
    size = len(source)
    spans: list[tuple[int, int]] = []

    def skip_comment(index: int) -> int:
        if source.startswith("//", index):
            stop = source.find("\n", index + 2)
            return size if stop < 0 else stop
        if source.startswith("/*", index):
            index += 2
            depth = 1
            while index < size and depth:
                if source.startswith("/*", index):
                    depth += 1
                    index += 2
                elif source.startswith("*/", index):
                    depth -= 1
                    index += 2
                else:
                    index += 1
            if depth:
                raise ValueError("unterminated Kotlin block comment")
            return index
        return index

    def skip_character(index: int) -> int:
        index += 1
        while index < size:
            if source[index] == "\\":
                index += 2
            elif source[index] == "'":
                return index + 1
            elif source[index] == "\n":
                raise ValueError("unterminated Kotlin character literal")
            else:
                index += 1
        raise ValueError("unterminated Kotlin character literal")

    def scan_string(index: int) -> int:
        raw = source.startswith('"""', index)
        delimiter = '"""' if raw else '"'
        index += len(delimiter)
        while index < size:
            if source.startswith(delimiter, index):
                return index + len(delimiter)
            if not raw and source[index] == "\\":
                index += 2
                continue
            if source.startswith("${", index):
                expression_start = index + 2
                expression_end = scan_code(expression_start, closing=True)
                spans.append((expression_start, expression_end))
                index = expression_end + 1
            elif not raw and source[index] == "\n":
                raise ValueError("unterminated Kotlin quoted literal")
            else:
                index += 1
        raise ValueError("unterminated Kotlin string literal")

    def scan_code(index: int, *, closing: bool = False) -> int:
        depth = 0
        while index < size:
            after_comment = skip_comment(index)
            if after_comment != index:
                index = after_comment
                continue
            if source.startswith('"""', index) or source[index] == '"':
                index = scan_string(index)
                continue
            if source[index] == "'":
                index = skip_character(index)
                continue
            if source[index] == "{":
                depth += 1
            elif source[index] == "}" and closing:
                if depth == 0:
                    return index
                depth -= 1
            index += 1
        if closing:
            raise ValueError("unterminated Kotlin string template expression")
        return index

    scan_code(0)
    return sorted(spans)


def junit_template_runtime_aborts(source: str) -> list[tuple[int, str]]:
    """Map real JUnit aborts inside evaluated templates back to source lines."""
    spans = kotlin_template_expression_spans(source)
    violations: list[tuple[int, str]] = []
    appended_line = source.count("\n") + 2
    for begin, end in spans:
        expression = source[begin:end]
        # Reuse the exact JUnit import/typealias interpreter (PR #767).
        # The original snippet supplies its imports; the appended expression
        # is outside a quote, so lexical masking cannot hide executed calls.
        combined = source + "\n" + expression + "\n"
        for line, name in junit_runtime_aborts(combined):
            if line >= appended_line:
                source_line = source.count("\n", 0, begin) + line - appended_line + 1
                violations.append((source_line, name))
    return sorted(set(violations))


class KotlinJunitTemplateAbortContract(unittest.TestCase):
    def test_real_watch_tests_do_not_skip_inside_interpolations(self):
        paths = kotlin_test_paths()
        self.assertTrue(paths, "Kotlin test inventory must not disappear")
        violations = []
        for path in paths:
            self.assertTrue(path.is_file() and not path.is_symlink())
            for line, name in junit_template_runtime_aborts(path.read_text(encoding="utf-8")):
                violations.append(f"{path.relative_to(ROOT)}:{line}: {name}")
        self.assertEqual([], violations, "\n".join(violations))

    def test_executed_junit4_assume_inside_regular_interpolation_is_rejected(self):
        source = 'val s = "${org.junit.Assume.assumeTrue(false)}"\n'
        self.assertEqual(
            [(1, "org.junit.Assume.assumeTrue")],
            junit_template_runtime_aborts(source),
        )

    def test_imported_class_alias_inside_template_is_rejected(self):
        source = (
            "import org.junit.jupiter.api.Assumptions as Gate\n"
            'val s = "${Gate.assumeFalse(true)}"\n'
        )
        self.assertEqual(
            [(2, "Gate.assumeFalse")],
            junit_template_runtime_aborts(source),
        )

    def test_direct_abort_inside_raw_template_is_rejected(self):
        source = (
            'val s = """${org.opentest4j.TestAbortedException("skip")}"""\n'
        )
        self.assertEqual(
            [(1, "org.opentest4j.TestAbortedException")],
            junit_template_runtime_aborts(source),
        )

    def test_transitive_alias_remains_resolved_inside_interpolation(self):
        source = (
            "typealias Gate = org.junit.Assume\n"
            'val s = "${Gate.assumeNotNull(null)}"\n'
        )
        self.assertEqual([(2, "Gate.assumeNotNull")], junit_template_runtime_aborts(source))

    def test_nested_expression_braces_do_not_hide_an_assume_call(self):
        source = (
            'val s = "${if (false) { org.junit.Assume.assumeTrue(false) } else { Unit }}"\n'
        )
        self.assertEqual(
            [(1, "org.junit.Assume.assumeTrue")],
            junit_template_runtime_aborts(source),
        )

    def test_nested_string_interpolation_inside_expression_is_scanned(self):
        source = (
            'val s = "${"inner ${org.junit.Assume.assumeTrue(false)}"}"\n'
        )
        self.assertEqual(
            [(1, "org.junit.Assume.assumeTrue")],
            junit_template_runtime_aborts(source),
        )

    def test_escaped_dollar_in_regular_string_is_safe_literal(self):
        source = 'val s = "\\${org.junit.Assume.assumeTrue(false)}"\n'
        self.assertEqual([], junit_template_runtime_aborts(source))

    def test_backslash_does_not_escape_dollar_in_raw_kotlin_string(self):
        source = 'val s = """\\${org.junit.Assume.assumeTrue(false)}"""\n'
        self.assertEqual(
            [(1, "org.junit.Assume.assumeTrue")],
            junit_template_runtime_aborts(source),
        )

    def test_ordinary_variable_reference_is_not_template_expression(self):
        source = 'val s = "hello $name"\n'
        self.assertEqual([], junit_template_runtime_aborts(source))

    def test_inert_quoted_and_commented_phrases_are_not_code(self):
        source = (
            '// val fake = "${org.junit.Assume.assumeTrue(false)}"\n'
            '/* val fake = """${org.junit.Assume.assumeFalse(true)}""" */\n'
            'val fake = "org.junit.Assume.assumeTrue(false)"\n'
        )
        self.assertEqual([], junit_template_runtime_aborts(source))

    def test_unrelated_library_assumption_names_are_not_junit(self):
        source = (
            "import other.library.Assume\n"
            'val s = "${Assume.assumeTrue(false)}"\n'
        )
        self.assertEqual([], junit_template_runtime_aborts(source))

    def test_unclosed_expression_is_rejected(self):
        with self.assertRaises(ValueError):
            kotlin_template_expression_spans('val broken = "${something"')

    def test_unclosed_nested_comment_is_rejected(self):
        with self.assertRaises(ValueError):
            kotlin_template_expression_spans(
                'val s = "${ /* not closed }"\n'
            )

    def test_multiline_raw_template_reports_real_source_line(self):
        source = (
            'val raw = """first\n'
            "second\n"
            '${org.junit.Assume.assumeTrue(false)}\n'
            'last"""\n'
        )
        self.assertEqual(
            [(3, "org.junit.Assume.assumeTrue")],
            junit_template_runtime_aborts(source),
        )

    def test_extracted_template_span_excludes_delimiters(self):
        source = 'val x = "${doWork(2)}"\n'
        spans = kotlin_template_expression_spans(source)
        self.assertEqual(["doWork(2)"], [source[a:b] for a, b in spans])


if __name__ == "__main__":
    unittest.main()
