# Raise AI quality-validation: awaitable unittest method integrity

Python's ordinary `unittest.TestCase` cannot await coroutine test methods.
A method like `async def test_really_checks_something(self): ...` may get a
green unittest summary while its assertions are never executed. This
**independent test-only source contract** prevents that failure in Raise AI.

`tests/test_unawaited_unittest_coroutines_contract.py` analyzes real ASTs in
the Python quality test tree. It fails for:

- Async `test_*` methods declared in ordinary `unittest.TestCase` or its
  local subclasses (including imported module/class aliases).
- Async `test_*` methods inherited from local mixins by synchronous cases.
- Top-level async `test_*` functions, which unittest does not discover.
- Async `setUp` / `tearDown` / `setUpClass` / `tearDownClass` hooks, which are
  not awaited even by `IsolatedAsyncioTestCase`.
- Misplaced `asyncSetUp` / `asyncTearDown` on synchronous `TestCase`, or
  inherited coroutine lifecycle hooks from local mixins.
- Async module-level `setUpModule` / `tearDownModule`, which unittest does
  not await.
- Cases that select a synchronous `TestCase` base ahead of the asyncio base.

It permits coroutine tests and `asyncSetUp` / `asyncTearDown` on
`unittest.IsolatedAsyncioTestCase` and local derived suites,
ordinary synchronous `test_*` methods, helper coroutines without a test
prefix and source that contains examples only in strings. AST parse errors
fail closed.

## Verification

```bash
python3 -m unittest tests.test_unawaited_unittest_coroutines_contract -v
python3 tools/run_python_contracts.py
```

This is a static guard only and does not prove actual test execution. Hosted
All Python contracts CI on the exact head is the machine gate. It neither
touches nor replaces the Kotlin/JUnit guard merged in PR #763, the Watch app,
the gateway, or the frozen Watch 7 physical acceptance handoff.

The product acceptance gate remains [issue #34](https://github.com/Zennay/RaiseAI/issues/34):
real physical Galaxy Watch 7 Watch → VPS → model → Watch, 30 deliberate raise
and 100 representative non-trigger gestures, background/screen-off review.
**No physical PASS is implied.**

Ownership: two new test/docs paths only, base main at
`01d8f3965d78dda057cbdf60f241e201a4794691`. No active worker's source
paths, runtime state or running jobs are modified.
