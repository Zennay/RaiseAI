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
      async json() {
        return {
          model,
          choices: [{ message: { content: answer } }]
        };
      }
    };
  };
}

function httpResponse(status, body = {}) {
  return {
    ok: status >= 200 && status < 300,
    status,
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

test("transient OpenRouter 5xx is retried once and then succeeds", async () => {
  let calls = 0;
  const execute = createOpenRouterExecutor({
    apiKey: "test-key",
    retryDelayMs: 0,
    sleepImpl: async () => {},
    fetchImpl: async () => {
      calls += 1;
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

test("provider timeout fails fast without a second request", async () => {
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
    /timeout/
  );
  assert.equal(calls, 1);
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
