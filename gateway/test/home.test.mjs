import test from "node:test";
import assert from "node:assert/strict";
import http from "node:http";
import { createHandler } from "../src/app.mjs";
import { classifyIntent } from "../src/router.mjs";
import { createHomeExecutor } from "../src/connectors/home.mjs";

const GATEWAY_TOKEN = "gateway-token-abcdefghijklmnopqrstuvwxyz-123";
const BRIDGE_TOKEN = "bridge-token-abcdefghijklmnopqrstuvwxyz-123";
const CONFIG = {
  enabled: true,
  origin: "http://127.0.0.1:8123",
  token: BRIDGE_TOKEN,
  devicesJson: JSON.stringify({ woonkamer: "living-light-1" })
};
const COMMAND = "Zet de lampen in de woonkamer uit";
const DECISION = classifyIntent(COMMAND);

function accepted() {
  return Response.json({
    ok: true,
    status: "accepted",
    device_id: "living-light-1",
    action: "turn_off"
  }, { status: 202 });
}

async function withGateway(execute, callback) {
  const server = http.createServer(createHandler({ token: GATEWAY_TOKEN, execute }));
  await new Promise(resolve => server.listen(0, "127.0.0.1", resolve));
  try {
    const url = "http://127.0.0.1:" + server.address().port + "/v1/assistant";
    await callback(url);
  } finally {
    await new Promise(resolve => server.close(resolve));
  }
}

function gatewayPost(url, text, authorization = "Bearer " + GATEWAY_TOKEN) {
  return fetch(url, {
    method: "POST",
    headers: { "content-type": "application/json", authorization },
    body: JSON.stringify({ text })
  });
}

test("authenticated Home light request dispatches only a fixed allowlisted payload", async () => {
  const calls = [];
  const executeHome = createHomeExecutor({
    ...CONFIG,
    fetchImpl: async (url, options) => {
      calls.push({ url, options });
      return accepted();
    }
  });

  await withGateway(executeHome, async url => {
    const result = await gatewayPost(url, COMMAND);
    assert.equal(result.status, 200);
    const body = await result.json();
    assert.equal(body.route, "smart_home");
    assert.equal(body.execution.enabled, true);
    assert.equal(body.execution.provider, "google_home");
    assert.equal(body.execution.reason, "home_command_accepted");
    assert.match(body.answer, /nog niet geverifieerd/u);
  });

  assert.equal(calls.length, 1);
  assert.equal(calls[0].url, "http://127.0.0.1:8123/v1/light-actions");
  assert.equal(calls[0].options.method, "POST");
  assert.equal(calls[0].options.redirect, "error");
  assert.equal(calls[0].options.headers.authorization, "Bearer " + BRIDGE_TOKEN);
  assert.deepEqual(JSON.parse(calls[0].options.body), {
    device_id: "living-light-1",
    action: "turn_off"
  });
  assert.equal(calls[0].options.body.includes(COMMAND), false);
});

test("gateway authentication prevents Home dispatch before connector execution", async () => {
  let calls = 0;
  const executeHome = createHomeExecutor({
    ...CONFIG,
    fetchImpl: async () => {
      calls++;
      return accepted();
    }
  });

  await withGateway(executeHome, async url => {
    for (const authorization of ["", "Bearer bad-token"]) {
      const response = await gatewayPost(url, COMMAND, authorization);
      assert.equal(response.status, 401);
      assert.equal((await response.json()).error, "unauthorized");
    }
  });
  assert.equal(calls, 0);
});

test("feature is disabled by default and missing or malformed credentials fail closed", async () => {
  for (const options of [
    {},
    { ...CONFIG, enabled: false },
    { ...CONFIG, token: "" },
    { ...CONFIG, token: "short" },
    { ...CONFIG, origin: "https://bridge.example/path" },
    { ...CONFIG, origin: "http://example.com" },
    { ...CONFIG, origin: "https://bridge.example/../" },
    { ...CONFIG, devicesJson: '{"woonkamer":"../unsafe"}' },
    { ...CONFIG, devicesJson: '{"woonkamer":"same","keuken":"same"}' }
  ]) {
    let calls = 0;
    const executeHome = createHomeExecutor({
      ...options,
      fetchImpl: async () => {
        calls++;
        return accepted();
      }
    });
    const result = await executeHome(DECISION, COMMAND);
    assert.equal(result.enabled, false);
    assert.equal(calls, 0);
  }
});

test("unsupported, ambiguous or multi-target utterances do not actuate", async () => {
  let calls = 0;
  const executeHome = createHomeExecutor({
    ...CONFIG,
    fetchImpl: async () => {
      calls++;
      return accepted();
    }
  });
  for (const text of [
    "Zet de thermostaat op 20 graden",
    "Zet alle lampen uit",
    "Zet de lampen in de woonkamer en slaapkamer uit",
    "Zet de lampen in de woonkamer uit en open de voordeur",
    "lampen in de keuken aan",
    "Zet de lampen in de woonkamer aan; voer code uit"
  ]) {
    const result = await executeHome(classifyIntent(text), text);
    assert.equal(result.enabled, false);
  }
  assert.equal(calls, 0);
});

test("informational, current-info and zCloud routes never call the Home bridge", async () => {
  let calls = 0;
  const executeHome = createHomeExecutor({
    ...CONFIG,
    fetchImpl: async () => {
      calls++;
      return accepted();
    }
  });
  for (const text of [
    "Wat is de temperatuur in de woonkamer?",
    "Wat is het nieuws vandaag?",
    "Ga door met zCloud",
    "Zet de lampen in de woonkamer niet uit"
  ]) {
    const result = await executeHome(classifyIntent(text), text);
    assert.equal(result, null);
  }
  assert.equal(calls, 0);
});

test("unauthorized Home bridge, rejected actions and invalid ACKs never claim success", async () => {
  const responses = [
    [Response.json({ error: "secret" }, { status: 401 }), "home_bridge_unauthorized"],
    [Response.json({ error: "no" }, { status: 403 }), "home_bridge_unauthorized"],
    [Response.json({ error: "denied" }, { status: 422 }), "home_bridge_rejected"],
    [Response.json({ error: "failed" }, { status: 503 }), "home_bridge_rejected"],
    [Response.json({ ok: true, status: "executed", device_id: "living-light-1", action: "turn_off" }), "home_bridge_invalid_ack"],
    [Response.json({ ok: true, status: "accepted", device_id: "other-light", action: "turn_off" }), "home_bridge_invalid_ack"],
    [Response.json({ ok: true, status: "accepted", device_id: "living-light-1", action: "turn_on" }), "home_bridge_invalid_ack"],
    [new Response("not json", { status: 200, headers: { "content-type": "text/html" } }), "home_bridge_invalid_ack"],
    [new Response("x".repeat(4097), { status: 200, headers: { "content-type": "application/json" } }), "home_bridge_invalid_ack"]
  ];
  for (const [response, reason] of responses) {
    const executeHome = createHomeExecutor({ ...CONFIG, fetchImpl: async () => response });
    const result = await executeHome(DECISION, COMMAND);
    assert.equal(result.enabled, false);
    assert.equal(result.reason, reason);
    assert.equal(JSON.stringify(result).includes("secret"), false);
  }
});

test("network timeout and forbidden redirect failures are surfaced without secrets", async () => {
  for (const error of [new Error("bridge-token-is-private"), new DOMException("timeout", "TimeoutError")]) {
    const executeHome = createHomeExecutor({
      ...CONFIG,
      fetchImpl: async (_url, options) => {
        assert.equal(options.redirect, "error");
        assert.ok(options.signal);
        throw error;
      }
    });
    const result = await executeHome(DECISION, COMMAND);
    assert.equal(result.enabled, false);
    assert.equal(result.reason, "home_bridge_unavailable");
    assert.equal(JSON.stringify(result).includes(error.message), false);
  }
});

test("Home bridge never receives AI or zCloud routing despite matching text", async () => {
  let calls = 0;
  const executeHome = createHomeExecutor({
    ...CONFIG,
    fetchImpl: async () => {
      calls++;
      return accepted();
    }
  });
  const result = await executeHome({
    route: "smart_home",
    target: "zcloud.worker",
    connector: "zcloud"
  }, COMMAND);
  assert.equal(result.enabled, false);
  assert.equal(result.reason, "home_route_invalid");
  assert.equal(calls, 0);
});
