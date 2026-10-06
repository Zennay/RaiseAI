import test from "node:test";
import assert from "node:assert/strict";
import http from "node:http";
import { createHandler } from "../src/app.mjs";

const TOKEN = "test-token-abcdefghijklmnopqrstuvwxyz-123456";
const UUID_V4 =
  /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/u;

async function withServer(fn, options = {}) {
  const server = http.createServer(createHandler({ token: TOKEN, ...options }));
  await new Promise(resolve => server.listen(0, "127.0.0.1", resolve));
  const { port } = server.address();

  try {
    await fn("http://127.0.0.1:" + port);
  } finally {
    await new Promise(resolve => server.close(resolve));
  }
}

async function readJsonBytes(res) {
  const bytes = Buffer.from(await res.arrayBuffer());
  return {
    bytes,
    body: JSON.parse(bytes.toString("utf8"))
  };
}

function assertJsonResponseHeaders(res, bytes) {
  assert.equal(res.headers.get("content-type"), "application/json; charset=utf-8");
  assert.equal(res.headers.get("cache-control"), "no-store");
  assert.equal(res.headers.get("x-content-type-options"), "nosniff");
  assert.equal(Number(res.headers.get("content-length")), bytes.length);
}

test("assistant responses expose unique UUID request IDs and byte-correct JSON metadata", async () => {
  await withServer(async base => {
    const requestIds = [];

    for (let index = 0; index < 2; index += 1) {
      const res = await fetch(base + "/v1/assistant", {
        method: "POST",
        headers: {
          "content-type": "application/json",
          authorization: "Bearer " + TOKEN
        },
        body: JSON.stringify({ text: "Geef een kort antwoord" })
      });

      assert.equal(res.status, 200);
      const { bytes, body } = await readJsonBytes(res);
      assertJsonResponseHeaders(res, bytes);
      assert.match(body.requestId, UUID_V4);
      assert.equal(body.answer, "Café ☕");
      requestIds.push(body.requestId);
    }

    assert.notEqual(requestIds[0], requestIds[1]);
  }, {
    execute: async () => ({
      enabled: true,
      provider: "test-provider",
      model: "test-model",
      answer: "Café ☕"
    })
  });
});

test("public health responses keep the same non-cacheable byte-length contract", async () => {
  await withServer(async base => {
    const res = await fetch(base + "/health");
    assert.equal(res.status, 200);

    const { bytes, body } = await readJsonBytes(res);
    assertJsonResponseHeaders(res, bytes);
    assert.equal(body.ok, true);
    assert.equal(body.revision, "quality-contract-revision");
    assert.equal("requestId" in body, false);
  }, {
    revision: "quality-contract-revision"
  });
});

test("error responses retain UUID provenance without leaking bearer credentials", async () => {
  await withServer(async base => {
    const wrongToken = "wrong-token-abcdefghijklmnopqrstuvwxyz-123456";
    const res = await fetch(base + "/v1/assistant", {
      method: "POST",
      headers: {
        "content-type": "application/json",
        authorization: "Bearer " + wrongToken
      },
      body: JSON.stringify({ text: "Dit mag niet worden uitgevoerd" })
    });

    assert.equal(res.status, 401);
    const { bytes, body } = await readJsonBytes(res);
    assertJsonResponseHeaders(res, bytes);
    assert.equal(body.error, "unauthorized");
    assert.match(body.requestId, UUID_V4);

    const serialized = bytes.toString("utf8");
    assert.equal(serialized.includes(TOKEN), false);
    assert.equal(serialized.includes(wrongToken), false);
    assert.equal(res.headers.get("authorization"), null);
  });
});
