# Raise AI QA: JUnit aborts inside Kotlin string templates

## Confirmed source-analysis blind spot

Kotlin ordinary quoted text is inert; Kotlin string interpolation of the form `${ expression }` is **executable code**. The existing #767 JUnit assumption/abort guard masks all quoted content to prevent false positives from fixture strings. Without an additional pass, a test could embed `org.junit.Assume.assumeTrue(false)` or `org.opentest4j.TestAbortedException(...)` in a Kotlin string template, causing a runtime skip that the source-only guard never sees.

A new, *independent* Python test suite examines just the evaluated interpolation expressions. Its scanner understands regular vs triple-quoted strings, escaped dollars (normal strings only), nested braces, embedded Kotlin strings, nested interpolation, line comments, nested block comments, malformed source fail-closed handling and original line-number mapping. Each extracted expression is checked with the existing exact JUnit identity/import/typealias logic from #767, so similarly named non-JUnit libraries are not falsely rejected. It scans both Kotlin unit tests and androidTest source.

Run with `python3 -m unittest tests.test_kotlin_junit_template_abort_contract -v` or through `python3 tools/run_python_contracts.py`.

## Scope and proof boundary

This patch adds only `tests/test_kotlin_junit_template_abort_contract.py` and this note. No shared Kotlin lexer, existing worker-owned tests, Watch app/gateway, workflows or VPS services are changed. Hosted Python static checks cannot substitute for a true Android JVM test execution. Frozen v1.5.2 physical Watch acceptance issue #34 remains separate: actual Watch→VPS→provider→Watch, 30 intentional/100 non-trigger trials and screen-off/background verification. Source-only QA does not advance the product evidence score.
