import test from "node:test";
import assert from "node:assert/strict";
import http from "node:http";
import { createHandler } from "../src/app.mjs";

const TOKEN = "test-token-abcdefghijklmnopqrstuvwxyz-123456";

async function withServer(fn) {
  const server = http.createServer(createHandler({ token: TOKEN }));
  await new Promise(resolve => server.listen(0, "127.0.0.1", resolve));
  const { port } = server.address();

  try {
    await fn("http://127.0.0.1:" + port);
  } finally {
    await new Promise(resolve => server.close(resolve));
  }
}

test("health is public and minimal", async () => {
  await withServer(async base => {
    const res = await fetch(base + "/health");
    assert.equal(res.status, 200);
    assert.deepEqual(await res.json(), {
      ok: true,
      service: "raise-gateway",
      version: "0.1.0"
    });
  });
});

test("routing requires bearer auth", async () => {
  await withServer(async base => {
    const res = await fetch(base + "/v1/route", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ text: "Ga door met HaxLab" })
    });
    assert.equal(res.status, 401);
  });
});

test("authenticated request routes but does not fake execution", async () => {
  await withServer(async base => {
    const res = await fetch(base + "/v1/assistant", {
      method: "POST",
      headers: {
        "content-type": "application/json",
        authorization: "Bearer " + TOKEN
      },
      body: JSON.stringify({
        text: "Ga door met HaxLab en test de pipeline"
      })
    });
    assert.equal(res.status, 200);
    const body = await res.json();
    assert.equal(body.route, "zcloud_task");
    assert.equal(body.execution.enabled, false);
    assert.equal(body.execution.reason, "connector_not_configured");
  });
});
