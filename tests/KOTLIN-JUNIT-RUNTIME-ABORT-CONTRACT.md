# QA: Kotlin/JUnit runtime-abort and assumption guard

## Gap addressed

A JUnit test can be discovered, annotated with `@Test`, and counted towards the minimum 18-method Watch regression baseline, yet be silently skipped using `org.junit.Assume`, Jupiter `org.junit.jupiter.api.Assumptions`, or an explicit `org.opentest4j.TestAbortedException`. This bypasses the current Kotlin `@Ignore`/`@Disabled` static check. Tests would appear present without actually evaluating assertions.

The new Python-hosted, source-only quality contract rejects those constructs across **both** `app/src/test` and `app/src/androidTest`. It understands actual JUnit imports and aliases, method imports and wildcard static imports, fully qualified calls, alias chains, and the TestAbortedException constructor. It does not flag unrelated libraries with similarly named helpers. Nested comments, char/quoted strings and raw Kotlin string fixtures are masked, and malformed source fails closed.

Run the direct tests with `python3 -m unittest tests.test_kotlin_junit_runtime_abort_contract -v`, and the aggregate suite with `python3 tools/run_python_contracts.py`.

## Limits and ownership

Static detection cannot prove JVM tests actually executed and cannot inspect reflection or non-JUnit custom exception wrappers. Any legitimate platform-conditional Watch/JVM test must be reviewed and structured as a separate clearly gated suite, rather than silently aborting within core JUnit tests. Android build, self-hosted JVM execution and physical Watch acceptance are separate gates.

Two add-only files are changed by this PR: this documentation and `tests/test_kotlin_junit_runtime_abort_contract.py`. No Kotlin tests or production app sources, gateway, existing QA code, workflows, VPS services or worker ownership are altered. Most importantly the [frozen v1.5.2 physical acceptance](https://github.com/Zennay/RaiseAI/issues/34) still needs real Watch→VPS→model→Watch proof, 30 intentional/100 non-trigger trials and screen-off/background observations. This QA change cannot be counted as a hardware PASS or a project-percentage increase.
