import test from "node:test";
import assert from "node:assert/strict";
import { evaluateZCloudProbe } from "../deploy/smoke-policy.mjs";

function refusalExecution(overrides = {}) {
  return {
    enabled: false,
    provider: "zcloud",
    reason: "zcloud_custom_task_not_supported",
    ...overrides
  };
}

function unavailableExecution(overrides = {}) {
  return {
    enabled: false,
    provider: "zcloud",
    reason: "zcloud_unavailable",
    ...overrides
  };
}

test("healthy zCloud refusal is a strict pass", () => {
  assert.deepEqual(
    evaluateZCloudProbe({
      status: 200,
      json: {
        route: "zcloud_task",
        execution: refusalExecution()
      }
    }),
    {
      ok: true,
      degraded: false,
      reason: "zcloud_custom_task_not_supported"
    }
  );
});

test("zCloud unavailable is degraded but does not fail gateway deploy by default", () => {
  assert.deepEqual(
    evaluateZCloudProbe({
      status: 200,
      json: {
        route: "zcloud_task",
        execution: unavailableExecution()
      }
    }),
    {
      ok: true,
      degraded: true,
      reason: "zcloud_unavailable"
    }
  );
});

test("strict zCloud mode fails when dependency is unavailable", () => {
  const result = evaluateZCloudProbe({
    status: 200,
    json: {
      route: "zcloud_task",
      execution: unavailableExecution()
    },
    requireZCloud: true
  });

  assert.equal(result.ok, false);
  assert.equal(result.degraded, true);
  assert.equal(result.reason, "zcloud_unavailable");
});

test("zCloud HTTP failures never pass as degraded dependency evidence", () => {
  for (const status of [400, 401, 404, 429, 500, 503]) {
    assert.deepEqual(
      evaluateZCloudProbe({
        status,
        json: {
          route: "zcloud_task",
          execution: unavailableExecution()
        }
      }),
      {
        ok: false,
        degraded: false,
        reason: `zcloud_http_${status}`
      }
    );
  }
});

test("missing zCloud HTTP status fails closed", () => {
  assert.deepEqual(
    evaluateZCloudProbe({
      status: undefined,
      json: null
    }),
    {
      ok: false,
      degraded: false,
      reason: "zcloud_http_unknown"
    }
  );
});

test("accepted refusal must prove no zCloud command was enabled", () => {
  for (const enabled of [true, undefined, null]) {
    assert.deepEqual(
      evaluateZCloudProbe({
        status: 200,
        json: {
          route: "zcloud_task",
          execution: refusalExecution({ enabled })
        }
      }),
      {
        ok: false,
        degraded: false,
        reason: "unexpected_execution_enabled"
      }
    );
  }
});

test("degraded outage must prove no zCloud command was enabled", () => {
  for (const enabled of [true, undefined, null]) {
    assert.deepEqual(
      evaluateZCloudProbe({
        status: 200,
        json: {
          route: "zcloud_task",
          execution: unavailableExecution({ enabled })
        }
      }),
      {
        ok: false,
        degraded: false,
        reason: "unexpected_execution_enabled"
      }
    );
  }
});

test("unexpected provider never passes", () => {
  assert.deepEqual(
    evaluateZCloudProbe({
      status: 200,
      json: {
        route: "zcloud_task",
        execution: refusalExecution({ provider: "openrouter" })
      }
    }),
    {
      ok: false,
      degraded: false,
      reason: "unexpected_provider"
    }
  );
});

test("unexpected route never passes", () => {
  const result = evaluateZCloudProbe({
    status: 200,
    json: {
      route: "quick_ai",
      execution: refusalExecution()
    }
  });

  assert.equal(result.ok, false);
  assert.equal(result.degraded, false);
  assert.match(result.reason, /^unexpected_route_/);
});
