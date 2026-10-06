const API_URL = "https://api.openai.com/v1/responses";

function hasUsableApiKey(value) {
  return typeof value === "string" && value.length > 0 && !/\s/u.test(value);
}

function normalizeModelName(value) {
  if (typeof value !== "string") return null;
  const model = value.trim();
  if (!model || /\s/u.test(model)) return null;
  return model;
}

function upstreamFailure(message, cause) {
  const error = new Error(message, { cause });
  error.statusCode = 502;
  return error;
}

function outputText(response) {
  const output = Array.isArray(response?.output) ? response.output : [];
  const textChunks = [];
  const refusalChunks = [];

  for (const item of output) {
    if (
      item === null ||
      typeof item !== "object" ||
      Array.isArray(item) ||
      item.type !== "message" ||
      item.role !== "assistant"
    ) {
      continue;
    }

    const content = Array.isArray(item.content) ? item.content : [];

    for (const part of content) {
      if (part?.type === "output_text" && typeof part.text === "string") {
        const text = part.text.trim();
        if (text) textChunks.push(text);
      }

      if (part?.type === "refusal" && typeof part.refusal === "string") {
        const refusal = part.refusal.trim();
        if (refusal) refusalChunks.push(refusal);
      }
    }
  }

  if (textChunks.length) return textChunks.join("\n");
  return refusalChunks.length ? refusalChunks.join("\n") : null;
}

export function createOpenAIExecutor({
  apiKey,
  fastModel = "gpt-5.4-nano",
  deepModel = "gpt-5.4-mini",
  allowWebSearch = false,
  fetchImpl = globalThis.fetch
}) {
  return async function execute(decision, text) {
    const supported =
      decision.route === "quick_ai" ||
      decision.route === "deep_ai" ||
      decision.route === "current_info";

    if (!supported) return null;

    if (!hasUsableApiKey(apiKey)) {
      return {
        enabled: false,
        reason: "openai_not_configured"
      };
    }

    if (decision.route === "current_info" && !allowWebSearch) {
      return {
        enabled: false,
        reason: "web_search_not_enabled"
      };
    }

    const model = normalizeModelName(
      decision.route === "deep_ai" ? deepModel : fastModel
    );

    if (!model) {
      return {
        enabled: false,
        reason: "openai_model_config_invalid"
      };
    }

    const request = {
      model,
      input: text,
      max_output_tokens: decision.route === "deep_ai" ? 320 : 180
    };

    if (decision.route === "current_info") {
      request.tools = [{ type: "web_search" }];
    }

    let response;
    try {
      response = await fetchImpl(API_URL, {
        method: "POST",
        headers: {
          authorization: "Bearer " + apiKey,
          "content-type": "application/json"
        },
        body: JSON.stringify(request),
        signal: AbortSignal.timeout(9_000)
      });
    } catch (cause) {
      throw upstreamFailure("openai_request_failed", cause);
    }

    const body = await response.json().catch(() => ({}));

    if (!response.ok) {
      const error = new Error("openai_http_" + response.status);
      error.statusCode = 502;
      throw error;
    }

    const answer = outputText(body);
    if (!answer) {
      const error = new Error("openai_empty_response");
      error.statusCode = 502;
      throw error;
    }

    return {
      enabled: true,
      provider: "openai",
      model,
      answer
    };
  };
}