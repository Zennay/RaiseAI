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
