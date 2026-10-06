import test from "node:test";
import assert from "node:assert/strict";
import { createOpenAIExecutor } from "../src/providers/openai.mjs";

function responseHeaders(contentType = "application/json") {
  return {
    get(name) {
      return String(name).toLowerCase() === "content-type" ? contentType : null;
    }
  };
}

function fakeResponse(answer, calls) {
  return async (url, options) => {
    calls.push({ url, request: JSON.parse(options.body), signal: options.signal });
    return {
      ok: true,
      status: 200,
      headers: responseHeaders(),
      async json() {
        return {
          output: [{
            type: "message",
            role: "assistant",
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
  assert.ok(calls[0].signal instanceof AbortSignal);
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

test("OpenAI model config trims benign padding before provider calls", async () => {
  const calls = [];
  const execute = createOpenAIExecutor({
    apiKey: "test-key",
    fastModel: "  gpt-5.4-nano  ",
    fetchImpl: fakeResponse("ok", calls)
  });

  const result = await execute({ route: "quick_ai" }, "hoi");

  assert.equal(result.enabled, true);
  assert.equal(result.model, "gpt-5.4-nano");
  assert.equal(calls[0].request.model, "gpt-5.4-nano");
});

test("invalid OpenAI model config fails closed before provider calls", async () => {
  const cases = [
    { fastModel: "" },
    { fastModel: "bad model" },
    { deepModel: "\t" },
    { deepModel: 42 }
  ];

  for (const options of cases) {
    let called = false;
    const execute = createOpenAIExecutor({
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
    assert.equal(result.reason, "openai_model_config_invalid");
    assert.equal(called, false);
  }
});

test("OpenAI response model provenance is normalized or falls back when omitted", async () => {
  const padded = createOpenAIExecutor({
    apiKey: "test-key",
    fetchImpl: async () => ({
      ok: true,
      status: 200,
      headers: responseHeaders(),
      async json() {
        return {
          model: "  gpt-5.4-nano-2026-09-01  ",
          output: [{
            type: "message",
            role: "assistant",
            content: [{ type: "output_text", text: "ok" }]
          }]
        };
      }
    })
  });

  const paddedResult = await padded({ route: "quick_ai" }, "hoi");
  assert.equal(paddedResult.model, "gpt-5.4-nano-2026-09-01");

  const omitted = createOpenAIExecutor({
    apiKey: "test-key",
    fetchImpl: fakeResponse("ok", [])
  });

  const omittedResult = await omitted({ route: "quick_ai" }, "hoi");
  assert.equal(omittedResult.model, "gpt-5.4-nano");
});

test("OpenAI response model must match the requested model or dated snapshot", async () => {
  for (const responseModel of [
    "gpt-5.4-mini",
    "openai/gpt-5.4-nano",
    "gpt-5.4-nano-preview",
    "gpt-5.4-nano-2026-9-01",
    "gpt-5.4-nano-2026-09-01-extra"
  ]) {
    const execute = createOpenAIExecutor({
      apiKey: "test-key",
      fetchImpl: async () => ({
        ok: true,
        status: 200,
        headers: responseHeaders(),
        async json() {
          return {
            model: responseModel,
            output: [{
              type: "message",
              role: "assistant",
              content: [{ type: "output_text", text: "must not pass" }]
            }]
          };
        }
      })
    });

    await assert.rejects(
      execute({ route: "quick_ai" }, "hoi"),
      error => {
        assert.equal(error.message, "openai_invalid_response");
        assert.equal(error.statusCode, 502);
        return true;
      }
    );
  }
});

test("malformed OpenAI response model fails closed", async () => {
  for (const model of ["", "bad model", 42, {}]) {
    const execute = createOpenAIExecutor({
      apiKey: "test-key",
      fetchImpl: async () => ({
        ok: true,
        status: 200,
        headers: responseHeaders(),
        async json() {
          return {
            model,
            output: [{
              type: "message",
              role: "assistant",
              content: [{ type: "output_text", text: "must not pass" }]
            }]
          };
        }
      })
    });

    await assert.rejects(
      execute({ route: "quick_ai" }, "hoi"),
      error => {
        assert.equal(error.message, "openai_invalid_response");
        assert.equal(error.statusCode, 502);
        return true;
      }
    );
  }
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
      headers: responseHeaders(),
      async json() {
        return {
          output: [
            {
              type: "reasoning",
              summary: []
            },
            {
              type: "message",
              role: "assistant",
              content: [
                { type: "output_text", text: "Eerste regel." },
                { type: "refusal", refusal: "ignored non-text part" },
                { type: "output_text", text: "Tweede regel." }
              ]
            },
            {
              type: "message",
              role: "assistant",
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
      headers: responseHeaders(),
      async json() {
        return {
          output: [{
            type: "message",
            role: "assistant",
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
      headers: responseHeaders(),
      async json() {
        return {
          output: [{
            type: "message",
            role: "assistant",
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

test("OpenAI output text is accepted only from assistant message items", async () => {
  const invalidBodies = [
    {
      output: [{
        type: "reasoning",
        role: "assistant",
        content: [{ type: "output_text", text: "must not pass" }]
      }]
    },
    {
      output: [{
        type: "message",
        role: "user",
        content: [{ type: "output_text", text: "must not pass" }]
      }]
    },
    {
      output: [{
        type: "function_call",
        role: "assistant",
        content: [{ type: "output_text", text: "must not pass" }]
      }]
    }
  ];

  for (const body of invalidBodies) {
    const execute = createOpenAIExecutor({
      apiKey: "test-key",
      fetchImpl: async () => ({
        ok: true,
        status: 200,
        headers: responseHeaders(),
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
        headers: responseHeaders(),
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


test("successful OpenAI responses require a JSON media type", async () => {
  for (const contentType of [null, "", "text/plain", "text/html; charset=utf-8"]) {
    let jsonCalls = 0;
    const execute = createOpenAIExecutor({
      apiKey: "test-key",
      fetchImpl: async () => ({
        ok: true,
        status: 200,
        headers: responseHeaders(contentType),
        async json() {
          jsonCalls += 1;
          return {
            output: [{
              content: [{ type: "output_text", text: "must not be trusted" }]
            }]
          };
        }
      })
    });

    await assert.rejects(
      execute({ route: "quick_ai" }, "hoi"),
      error => {
        assert.equal(error.message, "openai_invalid_response");
        assert.equal(error.statusCode, 502);
        return true;
      }
    );
    assert.equal(jsonCalls, 0);
  }
});

test("OpenAI accepts case-insensitive JSON media types with parameters", async () => {
  const execute = createOpenAIExecutor({
    apiKey: "test-key",
    fetchImpl: async () => ({
      ok: true,
      status: 200,
      headers: responseHeaders("Application/JSON; charset=UTF-8"),
      async json() {
        return {
          output: [{
            type: "message",
            role: "assistant",
            content: [{ type: "output_text", text: "geldig antwoord" }]
          }]
        };
      }
    })
  });

  const result = await execute({ route: "quick_ai" }, "hoi");
  assert.equal(result.answer, "geldig antwoord");
});

test("non-JSON OpenAI HTTP failures retain their HTTP failure classification", async () => {
  let jsonCalls = 0;
  const execute = createOpenAIExecutor({
    apiKey: "test-key",
    fetchImpl: async () => ({
      ok: false,
      status: 429,
      headers: responseHeaders("text/html"),
      async json() {
        jsonCalls += 1;
        throw new Error("must not parse non-JSON error body");
      }
    })
  });

  await assert.rejects(
    execute({ route: "quick_ai" }, "hoi"),
    error => {
      assert.equal(error.message, "openai_http_429");
      assert.equal(error.statusCode, 502);
      return true;
    }
  );
  assert.equal(jsonCalls, 0);
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


function streamedOpenAIResponse(bodyBytes, {
  contentType = "application/json",
  contentLength = null,
  status = 200
} = {}) {
  const headers = { "content-type": contentType };
  if (contentLength !== null) headers["content-length"] = String(contentLength);
  return new Response(bodyBytes, { status, headers });
}

function validOpenAIBody(answer = "ok") {
  return {
    model: "gpt-5.4-nano",
    output: [{
      type: "message",
      role: "assistant",
      content: [{ type: "output_text", text: answer }]
    }]
  };
}

test("OpenAI streams successful JSON through a 64 KiB response budget", async () => {
  const payload = Buffer.from(JSON.stringify(validOpenAIBody("bounded")), "utf8");
  const execute = createOpenAIExecutor({
    apiKey: "test-key",
    fetchImpl: async () => streamedOpenAIResponse(payload)
  });

  const result = await execute({ route: "quick_ai" }, "hoi");
  assert.equal(result.answer, "bounded");
});

test("OpenAI rejects oversized declared response bodies before parsing", async () => {
  const payload = Buffer.from(JSON.stringify(validOpenAIBody()), "utf8");
  const execute = createOpenAIExecutor({
    apiKey: "test-key",
    fetchImpl: async () => streamedOpenAIResponse(payload, {
      contentLength: (64 * 1024) + 1
    })
  });

  await assert.rejects(
    execute({ route: "quick_ai" }, "hoi"),
    error => {
      assert.equal(error.message, "openai_invalid_response");
      assert.equal(error.statusCode, 502);
      return true;
    }
  );
});

test("OpenAI rejects streamed bodies that exceed the byte budget without Content-Length", async () => {
  const oversized = {
    ...validOpenAIBody(),
    padding: "x".repeat(70 * 1024)
  };
  const payload = Buffer.from(JSON.stringify(oversized), "utf8");
  const execute = createOpenAIExecutor({
    apiKey: "test-key",
    fetchImpl: async () => streamedOpenAIResponse(payload)
  });

  await assert.rejects(
    execute({ route: "quick_ai" }, "hoi"),
    error => {
      assert.equal(error.message, "openai_invalid_response");
      assert.equal(error.statusCode, 502);
      return true;
    }
  );
});

test("OpenAI rejects incoherent Content-Length and invalid UTF-8", async () => {
  const validPayload = Buffer.from(JSON.stringify(validOpenAIBody()), "utf8");
  const mismatched = createOpenAIExecutor({
    apiKey: "test-key",
    fetchImpl: async () => streamedOpenAIResponse(validPayload, {
      contentLength: validPayload.length + 1
    })
  });

  await assert.rejects(
    mismatched({ route: "quick_ai" }, "hoi"),
    error => {
      assert.equal(error.message, "openai_invalid_response");
      assert.equal(error.statusCode, 502);
      return true;
    }
  );

  const invalidUtf8 = createOpenAIExecutor({
    apiKey: "test-key",
    fetchImpl: async () => streamedOpenAIResponse(
      new Uint8Array([0x7b, 0x22, 0x78, 0x22, 0x3a, 0x22, 0xc3, 0x28, 0x22, 0x7d])
    )
  });

  await assert.rejects(
    invalidUtf8({ route: "quick_ai" }, "hoi"),
    error => {
      assert.equal(error.message, "openai_invalid_response");
      assert.equal(error.statusCode, 502);
      return true;
    }
  );
});

test("OpenAI ignores provider error bodies and preserves HTTP failure classification", async () => {
  const oversizedError = Buffer.alloc(70 * 1024, 0x78);
  const execute = createOpenAIExecutor({
    apiKey: "test-key",
    fetchImpl: async () => streamedOpenAIResponse(oversizedError, {
      contentType: "application/json",
      status: 503
    })
  });

  await assert.rejects(
    execute({ route: "quick_ai" }, "hoi"),
    error => {
      assert.equal(error.message, "openai_http_503");
      assert.equal(error.statusCode, 502);
      return true;
    }
  );
});
