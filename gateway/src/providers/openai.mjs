const API_URL = "https://api.openai.com/v1/responses";

function hasUsableApiKey(value) {
  return typeof value === "string" && value.length > 0 && !/\s/u.test(value);
}

function outputText(response) {
  const output = Array.isArray(response?.output) ? response.output : [];
  const chunks = [];

  for (const item of output) {
    const content = Array.isArray(item?.content) ? item.content : [];

    for (const part of content) {
      if (part?.type === "output_text" && typeof part.text === "string") {
        const text = part.text.trim();
        if (text) chunks.push(text);
      }
    }
  }

  return chunks.length ? chunks.join("\n") : null;
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

    const model = decision.route === "deep_ai" ? deepModel : fastModel;
    const request = {
      model,
      input: text,
      max_output_tokens: decision.route === "deep_ai" ? 320 : 180
    };

    if (decision.route === "current_info") {
      request.tools = [{ type: "web_search" }];
    }

    const response = await fetchImpl(API_URL, {
      method: "POST",
      headers: {
        authorization: "Bearer " + apiKey,
        "content-type": "application/json"
      },
      body: JSON.stringify(request),
      signal: AbortSignal.timeout(9_000)
    });

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