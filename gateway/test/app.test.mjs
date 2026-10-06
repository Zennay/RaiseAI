import test from "node:test";
import assert from "node:assert/strict";
import http from "node:http";
import { createHandler } from "../src/app.mjs";

const TOKEN = "test-token-abcdefghijklmnopqrstuvwxyz-123456";

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

test("health is public and includes deploy revision", async () => {
  await withServer(async base => {
    const res = await fetch(base + "/health");
    assert.equal(res.status, 200);
    assert.deepEqual(await res.json(), {
      ok: true,
      service: "raise-gateway",
      version: "0.1.0",
      revision: "test-revision-123"
    });
  }, { revision: "test-revision-123" });
});

test("health revision defaults to unknown", async () => {
  await withServer(async base => {
    const res = await fetch(base + "/health");
    assert.equal(res.status, 200);
    const body = await res.json();
    assert.equal(body.revision, "unknown");
    assert.equal("token" in body, false);
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

test("rejects non-object JSON bodies before routing", async () => {
  let executeCalls = 0;

  await withServer(async base => {
    for (const payload of [null, [], 42, "question"]) {
      const res = await fetch(base + "/v1/assistant", {
        method: "POST",
        headers: {
          "content-type": "application/json",
          authorization: "Bearer " + TOKEN
        },
        body: JSON.stringify(payload)
      });

      assert.equal(res.status, 400);
      const body = await res.json();
      assert.equal(body.error, "invalid_request");
    }
  }, {
    execute: async () => {
      executeCalls += 1;
      return { enabled: true, answer: "must not run" };
    }
  });

  assert.equal(executeCalls, 0);
});

test("rejects non-string text before routing", async () => {
  let executeCalls = 0;

  await withServer(async base => {
    for (const text of [123, true, {}, ["question"]]) {
      const res = await fetch(base + "/v1/assistant", {
        method: "POST",
        headers: {
          "content-type": "application/json",
          authorization: "Bearer " + TOKEN
        },
        body: JSON.stringify({ text })
      });

      assert.equal(res.status, 400);
      const body = await res.json();
      assert.equal(body.error, "invalid_text");
    }
  }, {
    execute: async () => {
      executeCalls += 1;
      return { enabled: true, answer: "must not run" };
    }
  });

  assert.equal(executeCalls, 0);
});

test("missing and whitespace-only text retain text_required contract", async () => {
  await withServer(async base => {
    for (const payload of [{}, { text: "   \n\t" }]) {
      const res = await fetch(base + "/v1/assistant", {
        method: "POST",
        headers: {
          "content-type": "application/json",
          authorization: "Bearer " + TOKEN
        },
        body: JSON.stringify(payload)
      });

      assert.equal(res.status, 400);
      const body = await res.json();
      assert.equal(body.error, "text_required");
    }
  });
});
