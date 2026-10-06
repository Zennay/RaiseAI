import test from "node:test";
import assert from "node:assert/strict";
import http from "node:http";
import { createHandler, createRateLimiter } from "../src/app.mjs";

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

async function rawPost(base, headers, chunks = []) {
  return new Promise((resolve, reject) => {
    const req = http.request(base + "/v1/assistant", {
      method: "POST",
      headers: {
        "content-type": "application/json",
        authorization: "Bearer " + TOKEN,
        ...headers
      }
    }, res => {
      const responseChunks = [];
      res.on("data", chunk => responseChunks.push(chunk));
      res.on("end", () => {
        try {
          resolve({
            status: res.statusCode,
            body: JSON.parse(Buffer.concat(responseChunks).toString("utf8"))
          });
        } catch (error) {
          reject(error);
        }
      });
    });

    req.on("error", reject);
    for (const chunk of chunks) req.write(chunk);
    req.end();
  });
}

test("rate limiter caps active client buckets and resets them on minute rollover", () => {
  const limiter = createRateLimiter({ requestsPerMinute: 2, maxBuckets: 3 });

  assert.equal(limiter.allow("client-a", 100), true);
  assert.equal(limiter.allow("client-b", 100), true);
  assert.equal(limiter.allow("client-c", 100), true);
  assert.equal(limiter.allow("client-d", 100), false);

  assert.equal(limiter.allow("client-a", 100), true);
  assert.equal(limiter.allow("client-a", 100), false);

  assert.equal(limiter.allow("client-d", 101), true);
  assert.equal(limiter.allow("client-e", 101), true);
  assert.equal(limiter.allow("client-f", 101), true);
  assert.equal(limiter.allow("client-g", 101), false);
});

test("rate limiter fails closed on invalid minute input and invalid configuration", () => {
  const limiter = createRateLimiter({ requestsPerMinute: 1, maxBuckets: 1 });
  assert.equal(limiter.allow("client-a", Number.NaN), false);
  assert.equal(limiter.allow("client-a", 1.5), false);

  for (const options of [
    { requestsPerMinute: 0, maxBuckets: 1 },
    { requestsPerMinute: 1.5, maxBuckets: 1 },
    { requestsPerMinute: 1, maxBuckets: 0 },
    { requestsPerMinute: 1, maxBuckets: Number.MAX_SAFE_INTEGER + 1 }
  ]) {
    assert.throws(() => createRateLimiter(options), /invalid_rate_limit_config/);
  }
});

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


test("valid execution result preserves typed public fields", async () => {
  await withServer(async base => {
    const res = await fetch(base + "/v1/assistant", {
      method: "POST",
      headers: {
        "content-type": "application/json",
        authorization: "Bearer " + TOKEN
      },
      body: JSON.stringify({ text: "Wat is twee plus twee?" })
    });

    assert.equal(res.status, 200);
    const body = await res.json();
    assert.equal(body.status, "answered");
    assert.deepEqual(body.execution, {
      enabled: true,
      reason: null,
      provider: "test-provider",
      model: "test-model"
    });
    assert.equal(body.answer, "Vier.");
  }, {
    execute: async () => ({
      enabled: true,
      provider: "test-provider",
      model: "test-model",
      answer: "Vier.",
      ignoredInternalField: "not exposed"
    })
  });
});

test("malformed execution results fail closed as upstream errors", async () => {
  const malformedResults = [
    "enabled",
    [],
    {},
    { enabled: "true", answer: "unsafe" },
    { enabled: true, answer: { text: "unsafe" } },
    { enabled: true, provider: 42, answer: "unsafe" },
    { enabled: true, answer: "   " }
  ];

  for (const malformed of malformedResults) {
    await withServer(async base => {
      const res = await fetch(base + "/v1/assistant", {
        method: "POST",
        headers: {
          "content-type": "application/json",
          authorization: "Bearer " + TOKEN
        },
        body: JSON.stringify({ text: "Test malformed connector" })
      });

      assert.equal(res.status, 502);
      const body = await res.json();
      assert.equal(body.error, "internal_error");
      assert.equal("answer" in body, false);
      assert.equal("execution" in body, false);
    }, {
      execute: async () => malformed
    });
  }
});

test("execution results enforce bounded public response fields", async () => {
  const boundaryProvider = "p".repeat(256);
  const boundaryModel = "m".repeat(256);
  const boundaryAnswer = "a".repeat(4096);

  await withServer(async base => {
    const res = await fetch(base + "/v1/assistant", {
      method: "POST",
      headers: {
        "content-type": "application/json",
        authorization: "Bearer " + TOKEN
      },
      body: JSON.stringify({ text: "Wat is twee plus twee?" })
    });

    assert.equal(res.status, 200);
    const body = await res.json();
    assert.equal(body.execution.provider.length, 256);
    assert.equal(body.execution.model.length, 256);
    assert.equal(body.answer.length, 4096);
  }, {
    execute: async () => ({
      enabled: true,
      provider: boundaryProvider,
      model: boundaryModel,
      answer: boundaryAnswer
    })
  });

  const oversizedResults = [
    {
      enabled: true,
      provider: "p".repeat(257),
      model: "model",
      answer: "ok"
    },
    {
      enabled: true,
      provider: "provider",
      model: "m".repeat(257),
      answer: "ok"
    },
    {
      enabled: false,
      provider: "provider",
      reason: "r".repeat(257),
      answer: "fallback"
    },
    {
      enabled: true,
      provider: "provider",
      model: "model",
      answer: "a".repeat(4097)
    }
  ];

  for (const executionResult of oversizedResults) {
    await withServer(async base => {
      const res = await fetch(base + "/v1/assistant", {
        method: "POST",
        headers: {
          "content-type": "application/json",
          authorization: "Bearer " + TOKEN
        },
        body: JSON.stringify({ text: "Wat is twee plus twee?" })
      });

      assert.equal(res.status, 502);
      const body = await res.json();
      assert.equal(body.error, "internal_error");
      assert.equal("execution" in body, false);
      assert.equal("answer" in body, false);
    }, {
      execute: async () => executionResult
    });
  }
});

test("enabled AI execution without an answer fails closed", async () => {
  for (const routeText of [
    "Wat is twee plus twee?",
    "Analyseer deze architectuur",
    "Wat is het nieuws vandaag?"
  ]) {
    await withServer(async base => {
      const res = await fetch(base + "/v1/assistant", {
        method: "POST",
        headers: {
          "content-type": "application/json",
          authorization: "Bearer " + TOKEN
        },
        body: JSON.stringify({ text: routeText })
      });

      assert.equal(res.status, 502);
      const body = await res.json();
      assert.equal(body.error, "internal_error");
      assert.equal("answer" in body, false);
      assert.equal("execution" in body, false);
    }, {
      execute: async () => ({
        enabled: true,
        provider: "broken-provider",
        model: "broken-model"
      })
    });
  }
});

test("enabled AI execution requires canonical provider and model provenance", async () => {
  const malformed = [
    { enabled: true, answer: "ok", model: "test-model" },
    { enabled: true, answer: "ok", provider: "test-provider" },
    { enabled: true, answer: "ok", provider: "", model: "test-model" },
    { enabled: true, answer: "ok", provider: " test-provider", model: "test-model" },
    { enabled: true, answer: "ok", provider: "test-provider ", model: "test-model" },
    { enabled: true, answer: "ok", provider: "test-provider", model: "" },
    { enabled: true, answer: "ok", provider: "test-provider", model: " test-model" },
    { enabled: true, answer: "ok", provider: "test-provider", model: "test-model " },
    { enabled: true, answer: "ok", provider: "test provider", model: "test-model" },
    { enabled: true, answer: "ok", provider: "test-provider", model: "test\nmodel" }
  ];

  for (const executionResult of malformed) {
    await withServer(async base => {
      const res = await fetch(base + "/v1/assistant", {
        method: "POST",
        headers: {
          "content-type": "application/json",
          authorization: "Bearer " + TOKEN
        },
        body: JSON.stringify({ text: "Wat is twee plus twee?" })
      });

      assert.equal(res.status, 502);
      const body = await res.json();
      assert.equal(body.error, "internal_error");
      assert.equal("answer" in body, false);
      assert.equal("execution" in body, false);
    }, {
      execute: async () => executionResult
    });
  }
});

test("execution metadata tokens reject whitespace and control characters on every route", async () => {
  const malformedResults = [
    {
      enabled: true,
      provider: "google home"
    },
    {
      enabled: true,
      provider: "google_home\nproxy"
    },
    {
      enabled: false,
      provider: "zcloud",
      reason: "zcloud unavailable",
      answer: "Connector tijdelijk niet beschikbaar."
    },
    {
      enabled: false,
      provider: "zcloud",
      reason: "zcloud_unavailable\t",
      answer: "Connector tijdelijk niet beschikbaar."
    },
    {
      enabled: true,
      provider: "google_home",
      model: "unexpected model"
    }
  ];

  for (const executionResult of malformedResults) {
    await withServer(async base => {
      const res = await fetch(base + "/v1/assistant", {
        method: "POST",
        headers: {
          "content-type": "application/json",
          authorization: "Bearer " + TOKEN
        },
        body: JSON.stringify({ text: "Zet de lampen in de woonkamer uit" })
      });

      assert.equal(res.status, 502);
      const body = await res.json();
      assert.equal(body.error, "internal_error");
      assert.equal("execution" in body, false);
      assert.equal("answer" in body, false);
    }, {
      execute: async () => executionResult
    });
  }
});

test("non-AI routed execution may remain answerless", async () => {
  await withServer(async base => {
    const res = await fetch(base + "/v1/assistant", {
      method: "POST",
      headers: {
        "content-type": "application/json",
        authorization: "Bearer " + TOKEN
      },
      body: JSON.stringify({ text: "Zet de lampen in de woonkamer uit" })
    });

    assert.equal(res.status, 200);
    const body = await res.json();
    assert.equal(body.route, "smart_home");
    assert.equal(body.status, "routed");
    assert.equal(body.execution.enabled, true);
    assert.equal(body.answer, null);
  }, {
    execute: async () => ({
      enabled: true,
      provider: "google_home"
    })
  });
});

test("disabled connector result may return a user-facing string without claiming enabled", async () => {
  await withServer(async base => {
    const res = await fetch(base + "/v1/assistant", {
      method: "POST",
      headers: {
        "content-type": "application/json",
        authorization: "Bearer " + TOKEN
      },
      body: JSON.stringify({ text: "Ga door met zCloud" })
    });

    assert.equal(res.status, 200);
    const body = await res.json();
    assert.equal(body.status, "answered");
    assert.equal(body.execution.enabled, false);
    assert.equal(body.execution.reason, "connector_unavailable");
    assert.equal(body.answer, "Connector tijdelijk niet beschikbaar.");
  }, {
    execute: async () => ({
      enabled: false,
      reason: "connector_unavailable",
      provider: "test-provider",
      answer: "Connector tijdelijk niet beschikbaar."
    })
  });
});


test("handler rejects unsafe configured gateway tokens", () => {
  for (const token of [
    "x".repeat(31),
    "x".repeat(32) + " ",
    "x".repeat(16) + "\t" + "y".repeat(16),
    "x".repeat(16) + "\n" + "y".repeat(16)
  ]) {
    assert.throws(
      () => createHandler({ token }),
      /at least 32 characters with no whitespace or control characters/
    );
  }

  assert.doesNotThrow(() => createHandler({ token: "A1-._~".repeat(6) }));
});

test("authenticated JSON endpoints reject unsupported media types before execution", async () => {
  let executeCalls = 0;

  await withServer(async base => {
    for (const contentType of ["text/plain", "application/x-www-form-urlencoded"]) {
      const res = await fetch(base + "/v1/assistant", {
        method: "POST",
        headers: {
          "content-type": contentType,
          authorization: "Bearer " + TOKEN
        },
        body: JSON.stringify({ text: "Dit lijkt op JSON maar heeft het verkeerde mediatype." })
      });

      assert.equal(res.status, 415);
      const body = await res.json();
      assert.equal(body.error, "unsupported_media_type");
    }
  }, {
    execute: async () => {
      executeCalls += 1;
      return { enabled: true, answer: "must not run" };
    }
  });

  assert.equal(executeCalls, 0);
});

test("application/json media type is case-insensitive and permits parameters", async () => {
  await withServer(async base => {
    const res = await fetch(base + "/v1/assistant", {
      method: "POST",
      headers: {
        "content-type": "Application/JSON; charset=UTF-8",
        authorization: "Bearer " + TOKEN
      },
      body: JSON.stringify({ text: "Leg kubernetes pods simpel uit" })
    });

    assert.equal(res.status, 200);
    const body = await res.json();
    assert.equal(body.route, "quick_ai");
  });
});


test("executor errors cannot turn failure payloads into non-error HTTP statuses", async () => {
  for (const statusCode of [200, 204, 302, 399, 600, 999, "502"]) {
    await withServer(async base => {
      const res = await fetch(base + "/v1/assistant", {
        method: "POST",
        headers: {
          "content-type": "application/json",
          authorization: "Bearer " + TOKEN
        },
        body: JSON.stringify({ text: "Trigger executor failure" })
      });

      assert.equal(res.status, 500);
      const body = await res.json();
      assert.equal(body.error, "internal_error");
      assert.equal("answer" in body, false);
    }, {
      execute: async () => {
        const error = new Error("must_not_leak");
        error.statusCode = statusCode;
        throw error;
      }
    });
  }
});

test("non-Error executor throws become secret-safe internal errors", async () => {
  for (const thrown of [null, undefined, "private_failure", 42, false]) {
    await withServer(async base => {
      const res = await fetch(base + "/v1/assistant", {
        method: "POST",
        headers: {
          "content-type": "application/json",
          authorization: "Bearer " + TOKEN
        },
        body: JSON.stringify({ text: "Trigger non-Error executor failure" })
      });

      assert.equal(res.status, 500);
      const body = await res.json();
      assert.equal(body.error, "internal_error");
      assert.equal("answer" in body, false);
      assert.equal("execution" in body, false);
    }, {
      execute: async () => {
        throw thrown;
      }
    });
  }
});

test("valid upstream 4xx and 5xx error statuses remain failures", async () => {
  for (const statusCode of [400, 429, 502, 503, 599]) {
    await withServer(async base => {
      const res = await fetch(base + "/v1/assistant", {
        method: "POST",
        headers: {
          "content-type": "application/json",
          authorization: "Bearer " + TOKEN
        },
        body: JSON.stringify({ text: "Trigger bounded failure" })
      });

      assert.equal(res.status, statusCode);
      const body = await res.json();
      assert.equal(body.error, "internal_error");
    }, {
      execute: async () => {
        const error = new Error("private_upstream_detail");
        error.statusCode = statusCode;
        throw error;
      }
    });
  }
});

test("oversized declared bodies fail before the gateway waits for body bytes", async () => {
  let executeCalls = 0;

  await withServer(async base => {
    const response = await rawPost(base, {
      "content-length": String(16 * 1024 + 1)
    });

    assert.equal(response.status, 413);
    assert.equal(response.body.error, "payload_too_large");
    assert.equal("execution" in response.body, false);
  }, {
    execute: async () => {
      executeCalls += 1;
      return { enabled: true, answer: "must not run" };
    }
  });

  assert.equal(executeCalls, 0);
});

test("exactly 16 KiB is accepted by the body-size preflight", async () => {
  const prefix = '{"text":"';
  const suffix = '"}';
  const body = prefix + "a".repeat(16 * 1024 - prefix.length - suffix.length) + suffix;
  assert.equal(Buffer.byteLength(body), 16 * 1024);

  await withServer(async base => {
    const res = await fetch(base + "/v1/assistant", {
      method: "POST",
      headers: {
        "content-type": "application/json",
        authorization: "Bearer " + TOKEN
      },
      body
    });

    assert.equal(res.status, 413);
    const responseBody = await res.json();
    assert.equal(responseBody.error, "text_too_long");
  });
});

test("chunked bodies still enforce the streamed 16 KiB limit", async () => {
  let executeCalls = 0;

  await withServer(async base => {
    const response = await rawPost(
      base,
      { "transfer-encoding": "chunked" },
      [Buffer.alloc(16 * 1024 + 1, 0x61)]
    );

    assert.equal(response.status, 413);
    assert.equal(response.body.error, "payload_too_large");
    assert.equal("execution" in response.body, false);
  }, {
    execute: async () => {
      executeCalls += 1;
      return { enabled: true, answer: "must not run" };
    }
  });

  assert.equal(executeCalls, 0);
});

test("invalid JSON keeps its explicit public 400 contract", async () => {
  await withServer(async base => {
    const res = await fetch(base + "/v1/assistant", {
      method: "POST",
      headers: {
        "content-type": "application/json",
        authorization: "Bearer " + TOKEN
      },
      body: "{not-json"
    });

    assert.equal(res.status, 400);
    const body = await res.json();
    assert.equal(body.error, "invalid_json");
  });
});

test("invalid UTF-8 JSON bytes fail closed before execution", async () => {
  let executeCalls = 0;

  await withServer(async base => {
    const invalidUtf8Body = Buffer.concat([
      Buffer.from('{"text":"hello '),
      Buffer.from([0xc3, 0x28]),
      Buffer.from('"}')
    ]);

    const res = await fetch(base + "/v1/assistant", {
      method: "POST",
      headers: {
        "content-type": "application/json",
        authorization: "Bearer " + TOKEN
      },
      body: invalidUtf8Body
    });

    assert.equal(res.status, 400);
    const body = await res.json();
    assert.equal(body.error, "invalid_json");
  }, {
    execute: async () => {
      executeCalls += 1;
      return { enabled: true, answer: "must not run" };
    }
  });

  assert.equal(executeCalls, 0);
});
