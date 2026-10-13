# Raise AI — Watch Kotlin/JUnit discovery gate

## Observed coverage gap
Raise AI already rejects `@Ignore` / `@Disabled` in Kotlin tests (PR #763), but a file named `*Test.kt` can retain only helpers or comments after its last JUnit `@Test` method is accidentally removed. A green source linter does not mean the file still contributes an executable test.

This **quality-validation-only** regression closes that gap by scanning both `app/src/test` and `app/src/androidTest`: every `*Test.kt` must include at least one JUnit 4 or JUnit 5 `@Test` annotation attached to a Kotlin `fun` declaration. Real JUnit imports (including alias imports), full qualifier, annotation parameters and stacked annotations are supported. Tests prove that fabricated markers in comments, nested block comments, quoted strings or class/property annotations do not count. Invalid string syntax rejects.

Validation command: `python3 -m unittest tests.test_kotlin_junit_discovery_presence_contract -v` followed by `python3 tools/run_python_contracts.py`.

## Important limitation

This is **static source evidence**, not Android JVM execution proof or Watch hardware acceptance. It does not prove a test method executed its assertions; separate exact-head Android/JUnit and hosted aggregate quality checks remain authoritative for their respective boundaries. It does not affect or replace the frozen v1.5.2 Galaxy Watch 7 handoff, GitHub issue #34, the real Watch→VPS→provider→Watch trace, 30 intentional/100 non-trigger trials, or the screen-off/background UX gate.

Only two new files on current main are involved: this note and the standalone Python test. No Watch runtime, Kotlin tests, AndroidManifest, Gradle, gateway, CI workflow, VPS service, or worker-owned paths are changed. Keep independent code ownership and the test-only scope clear during review.
