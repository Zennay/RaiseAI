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

test("missing or whitespace-contaminated API key fails closed without a provider call", async () => {
  for (const apiKey of ["", " ", "\t", " test-key", "test-key ", "test key"]) {
    let called = false;
    const execute = createOpenAIExecutor({
      apiKey,
      fetchImpl: async () => {
        called = true;
        throw new Error("should not run");
      }
    });

    const result = await execute({ route: "quick_ai" }, "hoi");
    assert.equal(result.enabled, false);
    assert.equal(result.reason, "openai_not_configured");
    assert.equal(called, false);
  }
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

test("OpenAI response preserves every non-empty output_text block", async () => {
  const execute = createOpenAIExecutor({
    apiKey: "test-key",
    fetchImpl: async () => ({
      ok: true,
      status: 200,
      async json() {
        return {
          output: [
            {
              type: "reasoning",
              summary: []
            },
            {
              type: "message",
              content: [
                { type: "output_text", text: "Eerste regel." },
                { type: "refusal", refusal: "ignored non-text part" },
                { type: "output_text", text: "Tweede regel." }
              ]
            },
            {
              type: "message",
              content: [
                { type: "output_text", text: "   " },
                { type: "output_text", text: "Derde regel." }
              ]
            }
          ]
        };
      }
    })
  });

  const result = await execute({ route: "quick_ai" }, "Geef drie regels");

  assert.equal(result.answer, "Eerste regel.\nTweede regel.\nDerde regel.");
});

test("OpenAI refusal content is returned when no normal output_text exists", async () => {
  const execute = createOpenAIExecutor({
    apiKey: "test-key",
    fetchImpl: async () => ({
      ok: true,
      status: 200,
      async json() {
        return {
          output: [{
            type: "message",
            content: [
              { type: "refusal", refusal: "Ik kan daar niet mee helpen." },
              { type: "refusal", refusal: "Ik kan wel een veilig alternatief geven." }
            ]
          }]
        };
      }
    })
  });

  const result = await execute({ route: "quick_ai" }, "test refusal");

  assert.equal(
    result.answer,
    "Ik kan daar niet mee helpen.\nIk kan wel een veilig alternatief geven."
  );
  assert.equal(result.enabled, true);
  assert.equal(result.provider, "openai");
});

test("normal OpenAI output_text takes precedence over refusal content", async () => {
  const execute = createOpenAIExecutor({
    apiKey: "test-key",
    fetchImpl: async () => ({
      ok: true,
      status: 200,
      async json() {
        return {
          output: [{
            type: "message",
            content: [
              { type: "refusal", refusal: "Fallback refusal" },
              { type: "output_text", text: "Normaal antwoord." }
            ]
          }]
        };
      }
    })
  });

  const result = await execute({ route: "quick_ai" }, "test mixed response");

  assert.equal(result.answer, "Normaal antwoord.");
});

test("malformed successful OpenAI response shapes fail as upstream 502 errors", async () => {
  const malformedBodies = [
    null,
    {},
    { output: {} },
    { output: [null] },
    { output: [{ content: {} }] },
    { output: [{ content: [null, { type: "output_text", text: "   " }] }] }
  ];

  for (const body of malformedBodies) {
    const execute = createOpenAIExecutor({
      apiKey: "test-key",
      fetchImpl: async () => ({
        ok: true,
        status: 200,
        async json() {
          return body;
        }
      })
    });

    await assert.rejects(
      execute({ route: "quick_ai" }, "hoi"),
      error => {
        assert.equal(error.message, "openai_empty_response");
        assert.equal(error.statusCode, 502);
        return true;
      }
    );
  }
});


test("OpenAI transport failure is classified as upstream 502", async () => {
  const execute = createOpenAIExecutor({
    apiKey: "test-key",
    fetchImpl: async () => {
      throw new Error("socket reset");
    }
  });

  await assert.rejects(
    execute({ route: "quick_ai" }, "hoi"),
    error => {
      assert.equal(error.message, "openai_request_failed");
      assert.equal(error.statusCode, 502);
      assert.equal(error.cause?.message, "socket reset");
      return true;
    }
  );
});
