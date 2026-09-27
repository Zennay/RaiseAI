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

test("missing API key fails closed", async () => {
  const execute = createOpenRouterExecutor({ apiKey: "" });
  const result = await execute({ route: "quick_ai" }, "hoi");
  assert.equal(result.enabled, false);
  assert.equal(result.reason, "openrouter_not_configured");
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
