import test from "node:test";
import assert from "node:assert/strict";
import { createOpenRouterExecutor } from "../src/providers/openrouter.mjs";

function fakeResponse(answer, calls, model = "z-ai/glm-5.3-flash") {
  return async (url, options) => {
    calls.push({
      url,
      headers: options.headers,
      request: JSON.parse(options.body)
    });
    return {
      ok: true,
      status: 200,
      headers: {
        get(name) {
          return name.toLowerCase() === "content-type"
            ? "application/json; charset=utf-8"
            : null;
        }
      },
      async json() {
        return {
          model,
          choices: [{ message: { content: answer } }]
        };
      }
    };
  };
}

function httpResponse(status, body = {}, contentType = "application/json") {
  return {
    ok: status >= 200 && status < 300,
    status,
    headers: {
      get(name) {
        return name.toLowerCase() === "content-type" ? contentType : null;
      }
    },
    async json() {
      return body;
    }
  };
}

test("quick AI uses GLM 5.3 Flash with Gemini fallback by default", async () => {
  const calls = [];
  const execute = createOpenRouterExecutor({
    apiKey: "test-key",
    fetchImpl: fakeResponse("kort antwoord", calls)
  });

  const result = await execute({ route: "quick_ai" }, "Wat is DNS?");
  assert.equal(result.answer, "kort antwoord");
  assert.equal(result.provider, "openrouter");
  assert.equal(result.model, "z-ai/glm-5.3-flash");
  assert.deepEqual(calls[0].request.models, [
    "z-ai/glm-5.3-flash",
    "google/gemini-3.8-flash"
  ]);
  assert.deepEqual(calls[0].request.provider, {
    sort: "latency",
    preferred_max_latency: { p90: 3 },
    allow_fallbacks: true
  });
  assert.equal(calls[0].url, "https://openrouter.ai/api/v1/chat/completions");
});

test("deep AI supports an independently configurable model", async () => {
  const calls = [];
  const execute = createOpenRouterExecutor({
    apiKey: "test-key",
    deepModel: "z-ai/glm-5.3",
    fetchImpl: fakeResponse("dieper antwoord", calls, "z-ai/glm-5.3")
  });

  const result = await execute({ route: "deep_ai" }, "Analyseer deze architectuur");
  assert.equal(result.model, "z-ai/glm-5.3");
  assert.equal(calls[0].request.models[0], "z-ai/glm-5.3");
  assert.equal(calls[0].request.max_tokens, 320);
});

test("OpenRouter fallback list can be configured as CSV", async () => {
  const calls = [];
  const execute = createOpenRouterExecutor({
    apiKey: "test-key",
    fallbackModels: "google/gemini-3.8-flash, openai/gpt-5.6-luna",
    fetchImpl: fakeResponse("ok", calls)
  });

  await execute({ route: "quick_ai" }, "hoi");
  assert.deepEqual(calls[0].request.models, [
    "z-ai/glm-5.3-flash",
    "google/gemini-3.8-flash",
    "openai/gpt-5.6-luna"
  ]);
});

test("OpenRouter model config trims benign padding and deduplicates fallbacks", async () => {
  const calls = [];
  const execute = createOpenRouterExecutor({
    apiKey: "test-key",
    fastModel: "  z-ai/glm-5.3-flash  ",
    fallbackModels: [
      " google/gemini-3.8-flash ",
      "",
      "google/gemini-3.8-flash"
    ],
    fetchImpl: fakeResponse("ok", calls)
  });

  const result = await execute({ route: "quick_ai" }, "hoi");

  assert.equal(result.enabled, true);
  assert.deepEqual(calls[0].request.models, [
    "z-ai/glm-5.3-flash",
    "google/gemini-3.8-flash"
  ]);
});

test("invalid OpenRouter model config fails closed before provider calls", async () => {
  const cases = [
    { fastModel: "" },
    { fastModel: "bad model" },
    { deepModel: "\t" },
    { fallbackModels: ["google/gemini-3.8-flash", 42] },
    { fallbackModels: ["bad fallback"] }
  ];

  for (const options of cases) {
    let called = false;
    const execute = createOpenRouterExecutor({
      apiKey: "test-key",
      ...options,
      fetchImpl: async () => {
        called = true;
        throw new Error("should not run");
      }
    });

    const route = Object.hasOwn(options, "deepModel") ? "deep_ai" : "quick_ai";
    const result = await execute({ route }, "hoi");

    assert.equal(result.enabled, false);
    assert.equal(result.reason, "openrouter_model_config_invalid");
    assert.equal(called, false);
  }
});

test("OpenRouter response model provenance is normalized or falls back when omitted", async () => {
  const padded = createOpenRouterExecutor({
    apiKey: "test-key",
    fetchImpl: async () =>
      httpResponse(200, {
        model: "  z-ai/glm-5.3-flash  ",
        choices: [{ message: { content: "ok" } }]
      })
  });

  const paddedResult = await padded({ route: "quick_ai" }, "hoi");
  assert.equal(paddedResult.model, "z-ai/glm-5.3-flash");

  const omitted = createOpenRouterExecutor({
    apiKey: "test-key",
    fetchImpl: async () =>
      httpResponse(200, {
        choices: [{ message: { content: "ok" } }]
      })
  });

  const omittedResult = await omitted({ route: "quick_ai" }, "hoi");
  assert.equal(omittedResult.model, "z-ai/glm-5.3-flash");
});

test("malformed OpenRouter choices envelopes fail closed", async () => {
  const malformedBodies = [
    null,
    {},
    { choices: {} },
    { choices: { 0: { message: { content: "must not pass" } } } },
    { choices: [null] },
    { choices: [[]] },
    { choices: [{ message: null }] },
    { choices: [{ message: [] }] }
  ];

  for (const body of malformedBodies) {
    const execute = createOpenRouterExecutor({
      apiKey: "test-key",
      retryDelayMs: 0,
      sleepImpl: async () => {},
      fetchImpl: async () => httpResponse(200, body)
    });

    await assert.rejects(
      execute({ route: "quick_ai" }, "hoi"),
      error => {
        assert.equal(error.message, "openrouter_empty_response");
        assert.equal(error.statusCode, 502);
        return true;
      }
    );
  }
});

test("successful OpenRouter responses require the JSON media type", async () => {
  for (const contentType of [null, "", "text/plain", "text/html"]) {
    let calls = 0;
    const execute = createOpenRouterExecutor({
      apiKey: "test-key",
      retryDelayMs: 0,
      sleepImpl: async () => {},
      fetchImpl: async () => {
        calls += 1;
        return httpResponse(
          200,
          {
            model: "z-ai/glm-5.3-flash",
            choices: [{ message: { content: "must not pass" } }]
          },
          contentType
        );
      }
    });

    await assert.rejects(
      execute({ route: "quick_ai" }, "hoi"),
      error => {
        assert.equal(error.message, "openrouter_invalid_response");
        assert.equal(error.statusCode, 502);
        return true;
      }
    );
    assert.equal(calls, 1);
  }
});

test("OpenRouter accepts application/json case-insensitively with parameters", async () => {
  const execute = createOpenRouterExecutor({
    apiKey: "test-key",
    fetchImpl: async () =>
      httpResponse(
        200,
        {
          model: "z-ai/glm-5.3-flash",
          choices: [{ message: { content: "ok" } }]
        },
        "Application/JSON; charset=UTF-8"
      )
  });

  const result = await execute({ route: "quick_ai" }, "hoi");
  assert.equal(result.answer, "ok");
});

test("OpenRouter response model must belong to the requested model set", async () => {
  const execute = createOpenRouterExecutor({
    apiKey: "test-key",
    fallbackModels: ["google/gemini-3.8-flash"],
    retryDelayMs: 0,
    sleepImpl: async () => {},
    fetchImpl: async () =>
      httpResponse(200, {
        model: "unexpected/provider-model",
        choices: [{ message: { content: "untrusted" } }]
      })
  });

  await assert.rejects(
    execute({ route: "quick_ai" }, "hoi"),
    error => {
      assert.equal(error.message, "openrouter_invalid_response");
      assert.equal(error.statusCode, 502);
      return true;
    }
  );
});

test("OpenRouter accepts a configured fallback model as response provenance", async () => {
  const execute = createOpenRouterExecutor({
    apiKey: "test-key",
    fallbackModels: ["google/gemini-3.8-flash"],
    fetchImpl: async () =>
      httpResponse(200, {
        model: "google/gemini-3.8-flash",
        choices: [{ message: { content: "fallback ok" } }]
      })
  });

  const result = await execute({ route: "quick_ai" }, "hoi");
  assert.equal(result.model, "google/gemini-3.8-flash");
  assert.equal(result.answer, "fallback ok");
});

test("malformed OpenRouter response model fails closed", async () => {
  for (const model of ["", "bad model", 42, {}]) {
    let calls = 0;
    const execute = createOpenRouterExecutor({
      apiKey: "test-key",
      retryDelayMs: 0,
      sleepImpl: async () => {},
      fetchImpl: async () => {
        calls += 1;
        return httpResponse(200, {
          model,
          choices: [{ message: { content: "ok" } }]
        });
      }
    });

    await assert.rejects(
      execute({ route: "quick_ai" }, "hoi"),
      error => {
        assert.equal(error.message, "openrouter_invalid_response");
        assert.equal(error.statusCode, 502);
        return true;
      }
    );
    assert.equal(calls, 1);
  }
});

test("transient OpenRouter 5xx is retried once within one shared caller budget", async () => {
  let calls = 0;
  const signals = [];
  const execute = createOpenRouterExecutor({
    apiKey: "test-key",
    retryDelayMs: 0,
    sleepImpl: async () => {},
    fetchImpl: async (_url, options) => {
      calls += 1;
      signals.push(options.signal);
      if (calls === 1) return httpResponse(500, { error: "temporary" });
      return httpResponse(200, {
        model: "z-ai/glm-5.3-flash",
        choices: [{ message: { content: "gereed" } }]
      });
    }
  });

  const result = await execute({ route: "quick_ai" }, "hoi");
  assert.equal(calls, 2);
  assert.equal(result.answer, "gereed");
  assert.equal(signals.length, 2);
  assert.ok(signals[0] instanceof AbortSignal);
  assert.equal(signals[0], signals[1]);
});

test("transient fetch failure is retried once", async () => {
  let calls = 0;
  const execute = createOpenRouterExecutor({
    apiKey: "test-key",
    retryDelayMs: 0,
    sleepImpl: async () => {},
    fetchImpl: async () => {
      calls += 1;
      if (calls === 1) throw new Error("temporary_network_failure");
      return httpResponse(200, {
        model: "z-ai/glm-5.3-flash",
        choices: [{ message: { content: "ok" } }]
      });
    }
  });

  const result = await execute({ route: "quick_ai" }, "hoi");
  assert.equal(calls, 2);
  assert.equal(result.answer, "ok");
});

test("provider timeout fails fast as upstream 502 without a second request", async () => {
  let calls = 0;
  const execute = createOpenRouterExecutor({
    apiKey: "test-key",
    retryDelayMs: 0,
    sleepImpl: async () => {},
    fetchImpl: async () => {
      calls += 1;
      const error = new Error("The operation was aborted due to timeout");
      error.name = "TimeoutError";
      throw error;
    }
  });

  await assert.rejects(
    execute({ route: "quick_ai" }, "hoi"),
    error => {
      assert.equal(error.message, "openrouter_request_failed");
      assert.equal(error.statusCode, 502);
      assert.equal(error.cause?.name, "TimeoutError");
      return true;
    }
  );
  assert.equal(calls, 1);
});

test("persistent OpenRouter transport failure becomes upstream 502 after bounded retry", async () => {
  let calls = 0;
  const execute = createOpenRouterExecutor({
    apiKey: "test-key",
    retryDelayMs: 0,
    sleepImpl: async () => {},
    fetchImpl: async () => {
      calls += 1;
      throw new Error("connection refused");
    }
  });

  await assert.rejects(
    execute({ route: "quick_ai" }, "hoi"),
    error => {
      assert.equal(error.message, "openrouter_request_failed");
      assert.equal(error.statusCode, 502);
      assert.equal(error.cause?.message, "connection refused");
      return true;
    }
  );
  assert.equal(calls, 2);
});

test("permanent OpenRouter 4xx fails closed without retry", async () => {
  let calls = 0;
  const execute = createOpenRouterExecutor({
    apiKey: "test-key",
    retryDelayMs: 0,
    sleepImpl: async () => {},
    fetchImpl: async () => {
      calls += 1;
      return httpResponse(401, { error: "unauthorized" });
    }
  });

  await assert.rejects(
    execute({ route: "quick_ai" }, "hoi"),
    /openrouter_http_401/
  );
  assert.equal(calls, 1);
});

test("persistent OpenRouter 5xx still fails closed after bounded retry", async () => {
  let calls = 0;
  const execute = createOpenRouterExecutor({
    apiKey: "test-key",
    retryDelayMs: 0,
    sleepImpl: async () => {},
    fetchImpl: async () => {
      calls += 1;
      return httpResponse(503, { error: "unavailable" });
    }
  });

  await assert.rejects(
    execute({ route: "quick_ai" }, "hoi"),
    /openrouter_http_503/
  );
  assert.equal(calls, 2);
});

test("missing or whitespace-contaminated API key fails closed without a provider call", async () => {
  for (const apiKey of ["", " ", "\t", " test-key", "test-key ", "test key"]) {
    let called = false;
    const execute = createOpenRouterExecutor({
      apiKey,
      fetchImpl: async () => {
        called = true;
        throw new Error("should not run");
      }
    });

    const result = await execute({ route: "quick_ai" }, "hoi");
    assert.equal(result.enabled, false);
    assert.equal(result.reason, "openrouter_not_configured");
    assert.equal(called, false);
  }
});

test("web search is opt-in", async () => {
  let called = false;
  const execute = createOpenRouterExecutor({
    apiKey: "test-key",
    fetchImpl: async () => {
      called = true;
      throw new Error("should not run");
    }
  });

  const result = await execute({ route: "current_info" }, "nieuws vandaag");
  assert.equal(result.enabled, false);
  assert.equal(result.reason, "web_search_not_enabled");
  assert.equal(called, false);
});

test("enabled current-info route uses OpenRouter web search", async () => {
  const calls = [];
  const execute = createOpenRouterExecutor({
    apiKey: "test-key",
    allowWebSearch: true,
    fetchImpl: fakeResponse("actueel antwoord", calls)
  });

  const result = await execute({ route: "current_info" }, "nieuws vandaag");
  assert.equal(result.answer, "actueel antwoord");
  assert.deepEqual(calls[0].request.tools, [{ type: "openrouter:web_search" }]);
});

test("non-LLM routes never call OpenRouter", async () => {
  let called = false;
  const execute = createOpenRouterExecutor({
    apiKey: "test-key",
    fetchImpl: async () => {
      called = true;
      throw new Error("should not run");
    }
  });

  const result = await execute({ route: "smart_home" }, "lamp uit");
  assert.equal(result, null);
  assert.equal(called, false);
});
