# Raise AI — Kotlin/JUnit disabled-test quality gate

## Intent and ownership

This is a Python-hosted **quality-validation** guard for Kotlin test sources.
It is separate from the app-core Android activity owners, the Watch runner,
the frozen v1.5.2 physical handoff and the existing Python unittest skip gate.

A JUnit test annotated with `@org.junit.Ignore` (JUnit 4) or
`@org.junit.jupiter.api.Disabled` (JUnit 5) can vanish from effective
regression coverage while an unrelated CI job still reports success.
The new `tests/test_kotlin_junit_disable_contract.py` refuses those
annotations in `app/src/test/**/*.kt` and `app/src/androidTest/**/*.kt`.

Detection recognizes:
- Bare `@Ignore` and `@Disabled`, as well as fully-qualified JUnit forms.
- Kotlin `import ... as ...` annotation aliases and transitive
  `typealias` wrappers rooted in the disabled JUnit annotations.
- Kotlin annotation use-site targets such as `@get:Ignore`.
- Nested block comments, quoted literals and triple-quoted fixture strings
  are **not** treated as executable annotations.

The test guard fails closed on malformed or unreadable Kotlin test source
and refuses a disappearing Kotlin test inventory. It only reads checked-out
source files and does not change Watch app/gateway code or interact with a
device. Independent Python contract tests cover the scanner's negative and
positive fixtures.

## Run

```bash
python3 -m unittest tests.test_kotlin_junit_disable_contract -v
python3 tools/run_python_contracts.py
```

## Evidence hierarchy

This test establishes **source-level coverage integrity only**. It does not
prove that JUnit tests compiled or executed. Actual Android/JUnit success
requires the exact-head Raise Watch app CI job. Product acceptance still
requires the physical Galaxy Watch 7 frozen-v1.5.2 run and evidence in
[issue #34](https://github.com/Zennay/RaiseAI/issues/34): real
Watch → VPS → model → Watch, 30 intentional and 100 non-trigger gestures,
and screen-off/background UX checks. Never label an automated static
guard as an E2E or physical PASS.

## Review notes

- Base: main `eeaa51a93832a9d11668f3210c16e37785e0d541`.
- Add-only paths: this Markdown note and the new standalone Python test.
- No edits to `NativeVoiceActivity.kt`, gateway, existing Kotlin tests,
  quality workflows, scripts, physical tools, frozen release or issue #34.
- Hold merge until hosted exact-head Python contracts pass and an independent
  owner reviews the new scanner. Shared self-hosted Watch/JUnit queue proof
  must be reported separately.
