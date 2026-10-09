import test from "node:test";
import assert from "node:assert/strict";
import { createZCloudExecutor } from "../src/connectors/zcloud.mjs";

// A corrupt control-plane snapshot must never reach the privileged POST path.
// Keep these fixtures independent of server availability and device evidence.
const worker = (overrides = {}) => ({
  base_project_id: "cloud",
  project_id: "cloud::w1",
  worker_slot: 1,
  worker_count: 1,
  active: true,
  assignment_ready: true,
  desired_state: "running",
  name: "zCloud",
  ...overrides
});

const json = (body) => new Response(JSON.stringify(body), {
  status: 200,
  headers: { "content-type": "application/json; charset=utf-8" }
});

async function exercise(snapshot) {
  const calls = [];
  const execute = createZCloudExecutor({
    fetchImpl: async (url, options = {}) => {
      calls.push({ url, method: options.method ?? "GET", redirect: options.redirect });
      if (options.method === "POST") {
        return json({ ok: true, command_id: 1 });
      }
      return json(snapshot);
    }
  });
  const result = await execute({ route: "zcloud_task" }, "ga door met zcloud");
  return { result, calls };
}

test("valid complete snapshot can submit exactly one bounded control request", async () => {
  const { result, calls } = await exercise({
    projects: { "cloud::w1": worker() }
  });
  assert.equal(result.enabled, true);
  assert.deepEqual(calls.map(call => call.method), ["GET", "POST"]);
  assert.ok(calls.every(call => call.redirect === "error"));
});

for (const [label, projects] of [
  ["worker slot missing", { "cloud::w1": worker({ worker_count: 2 }) }],
  ["key differs from signed worker identity", { "cloud::w2": worker() }],
  ["active but not assignment-ready", { "cloud::w1": worker({ assignment_ready: false }) }],
  ["active while paused", { "cloud::w1": worker({ desired_state: "paused" }) }],
  ["noncanonical display name", { "cloud::w1": worker({ name: "LightUp" }) }],
  ["format control in display name", { "cloud::w1": worker({ name: "zCloud\u202e" }) }],
  ["nonintegral count", { "cloud::w1": worker({ worker_count: 1.5 }) }],
  ["unbounded count", { "cloud::w1": worker({ worker_count: Number.MAX_SAFE_INTEGER }) }]
]) {
  test(`invalid snapshot (${label}) fails closed without any POST`, async () => {
    const { result, calls } = await exercise({ projects });
    assert.equal(result.enabled, false);
    assert.equal(result.reason, "zcloud_targets_invalid");
    assert.deepEqual(calls.map(call => call.method), ["GET"]);
  });
}
