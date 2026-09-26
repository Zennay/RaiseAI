import test from "node:test";
import assert from "node:assert/strict";
import { createOpenAIExecutor } from "../src/providers/openai.mjs";

function fakeResponse(answer, calls) {
  return async (url, options) => {
    calls.push({ url, request: JSON.parse(options.body) });
    return {
      ok: true,
      status: 200,
      async json() {
        return {
          output: [{
            content: [{ type: "output_text", text: answer }]
          }]
        };
      }
    };
  };
}

test("quick AI uses nano by default", async () => {
  const calls = [];
  const execute = createOpenAIExecutor({
    apiKey: "test-key",
    fetchImpl: fakeResponse("kort antwoord", calls)
  });

  const result = await execute({ route: "quick_ai" }, "Wat is DNS?");
  assert.equal(result.answer, "kort antwoord");
  assert.equal(result.model, "gpt-5.4-nano");
  assert.equal(calls[0].request.model, "gpt-5.4-nano");
});

test("deep AI uses mini", async () => {
  const calls = [];
  const execute = createOpenAIExecutor({
    apiKey: "test-key",
    fetchImpl: fakeResponse("dieper antwoord", calls)
  });

  const result = await execute({ route: "deep_ai" }, "Analyseer deze architectuur");
  assert.equal(result.model, "gpt-5.4-mini");
  assert.equal(calls[0].request.max_output_tokens, 320);
});

test("web search is opt-in", async () => {
  let called = false;
  const execute = createOpenAIExecutor({
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

test("missing API key fails closed", async () => {
  const execute = createOpenAIExecutor({ apiKey: "" });
  const result = await execute({ route: "quick_ai" }, "hoi");
  assert.equal(result.enabled, false);
  assert.equal(result.reason, "openai_not_configured");
});

test("enabled current-info route requests web search explicitly", async () => {
  const calls = [];
  const execute = createOpenAIExecutor({
    apiKey: "test-key",
    allowWebSearch: true,
    fetchImpl: fakeResponse("actueel antwoord", calls)
  });

  const result = await execute({ route: "current_info" }, "nieuws vandaag");
  assert.equal(result.answer, "actueel antwoord");
  assert.deepEqual(calls[0].request.tools, [{ type: "web_search" }]);
});