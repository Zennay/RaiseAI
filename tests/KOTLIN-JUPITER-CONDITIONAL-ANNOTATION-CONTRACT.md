# Kotlin/JUnit Jupiter conditional test exclusion guard

## Why it is required
The Raise AI quality suite now rejects `@Ignore`/`@Disabled` (#763), runtime `Assume`/`Assumptions` or `TestAbortedException` (#767), and shrinking JUnit method inventories (#765/#766). Jupiter's **conditional test annotations** are a separate route to silently exclude an apparently valid test from execution depending on host OS, Java runtime, environment variables, system properties or native-image status.

This new offline Python test scans Watch `app/src/test` and `app/src/androidTest` Kotlin source for exact Jupiter condition annotation identities in `org.junit.jupiter.api.condition`. It covers OS, JRE, environment variable, system property, expression and native-image conditions, both `Enabled*` and `Disabled*`, including singular/plural forms. It recognizes fully qualified annotation names, explicit imports with aliases, wildcard imports, Kotlin annotation use-site labels and long typealias chains. Non-JUnit names in unrelated packages and quoted/commented fixture text do not trigger false alarms. Invalid Kotlin literals fail closed.

To execute:
- `python3 -m unittest tests.test_kotlin_junit_conditional_annotation_contract -v`
- `python3 tools/run_python_contracts.py`

## Validation limitations
This is **static source validation only**; the test does not build the Wear APK or prove that JUnit or the device ran. Legitimately OS-conditional platform tests require explicit segregation and approval, not hidden conditional excludes in the core suite. The watched baseline is frozen physical Galaxy Watch 7 v1.5.2; the real end-to-end flow, 30 intentional/100 non-trigger gestures, and screen-off/background UX still require real hardware as captured in [issue #34](https://github.com/Zennay/RaiseAI/issues/34).

No Watch app logic, existing Kotlin tests, other QA owners' sources, Gradle configuration, CI workflow, VPS or gateway is changed. Exactly two add-only paths: this note and `tests/test_kotlin_junit_conditional_annotation_contract.py`. Progress score must not increase due to these tests alone.
