# Raise AI quality gate: minimum Watch Kotlin/JUnit coverage

## Why this exists

PR #765 added a source-level guard requiring at least one real JUnit test method per Kotlin `*Test.kt` suite. That is necessary but insufficient: losing four of five existing tests would still pass. This follow-up protects the **original five canonical Watch unit-test suites** against silent partial removal, without changing their source files.

The static baseline is captured from real `main` source at `f3198aef81cf3d6e34426619c636592df884b4b6`:

| Suite | Minimum JUnit test methods |
| --- | ---: |
| AssistantModeStoreTest.kt | 5 |
| PinnedTlsTest.kt | 2 |
| RaiseGestureDetectorTest.kt | 4 |
| SensorTrialProgressTest.kt | 4 |
| VoiceRetryPolicyTest.kt | 3 |
| **Total protected floor** | **18** |

New Kotlin suites and additional tests are welcome. Removal, renaming or consolidation of protected tests requires an explicitly reviewed update to this baseline, not accidental disappearance. The test reuses the actual JUnit annotation parser from #765, so comments, fake imports and quoted strings cannot satisfy the floor.

Run: `python3 -m unittest tests.test_watch_junit_baseline_budget_contract -v` and `python3 tools/run_python_contracts.py`.

## Safety and ownership

- Two add-only paths: this note and a standalone Python quality regression.
- No edits to the five Kotlin test files, Android production code, gateway, workflows, running jobs, stored secrets, VPS or device.
- The baseline is only a source-integrity signal. **It is not proof that JUnit methods compiled or executed, nor that their assertions are effective.**
- The exact-head self-hosted Android/Watch test job must still run for JVM confidence; the main physical Galaxy Watch 7 acceptance gate remains [issue #34](https://github.com/Zennay/RaiseAI/issues/34), using the frozen v1.5.2 archive and real Watch→VPS→provider→Watch, 30 intentional/100 non-trigger trials and background/screen-off observations.
- Do not increase product acceptance/completeness score from this test-only work.

Base exact main SHA: `f3198aef81cf3d6e34426619c636592df884b4b6`.
