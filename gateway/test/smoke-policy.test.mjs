import test from "node:test";
import assert from "node:assert/strict";
import { evaluateZCloudProbe } from "../deploy/smoke-policy.mjs";

test("healthy zCloud refusal is a strict pass", () => {
  assert.deepEqual(
    evaluateZCloudProbe({
      status: 200,
      json: {
        route: "zcloud_task",
        execution: {
          provider: "zcloud",
          reason: "zcloud_custom_task_not_supported"
        }
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
        execution: {
          provider: "zcloud",
          reason: "zcloud_unavailable"
        }
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
      execution: {
        provider: "zcloud",
        reason: "zcloud_unavailable"
      }
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
          execution: {
            provider: "zcloud",
            reason: "zcloud_unavailable"
          }
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

test("unexpected route never passes", () => {
  const result = evaluateZCloudProbe({
    status: 200,
    json: {
      route: "quick_ai",
      execution: {
        provider: "zcloud",
        reason: "zcloud_custom_task_not_supported"
      }
    }
  });

  assert.equal(result.ok, false);
  assert.equal(result.degraded, false);
  assert.match(result.reason, /^unexpected_route_/);
});
