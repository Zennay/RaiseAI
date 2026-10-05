const API_URL = "https://openrouter.ai/api/v1/chat/completions";

function parseFallbackModels(value) {
  return String(value ?? "")
    .split(",")
    .map((model) => model.trim())
    .filter(Boolean);
}

function uniqueModels(models) {
  return [...new Set(models.filter(Boolean))];
}

function outputText(response) {
  const content = response?.choices?.[0]?.message?.content;
  if (typeof content === "string") {
    const text = content.trim();
    return text || null;
  }

  if (Array.isArray(content)) {
    const text = content
      .filter((part) => part?.type === "text" && typeof part.text === "string")
      .map((part) => part.text)
      .join("")
      .trim();
    return text || null;
  }

  return null;
}

function isRetryableStatus(status) {
  return status === 408 || status === 425 || status === 429 || status >= 500;
}

function isRetryableThrownError(error) {
  const name = String(error?.name ?? "");
  const message = String(error?.message ?? "");
  if (name === "TimeoutError" || name === "AbortError") return false;
  return !message.startsWith("openrouter_");
}

function defaultSleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

export function createOpenRouterExecutor({
  apiKey,
  fastModel = "z-ai/glm-5.3-flash",
  deepModel = "z-ai/glm-5.3-flash",
  fallbackModels = ["google/gemini-3.8-flash"],
  allowWebSearch = false,
  fetchImpl = globalThis.fetch,
  maxAttempts = 2,
  retryDelayMs = 250,
  sleepImpl = defaultSleep
}) {
  const fallbacks = Array.isArray(fallbackModels)
    ? fallbackModels
    : parseFallbackModels(fallbackModels);
  const attempts = Math.max(1, Math.min(Number(maxAttempts) || 1, 3));

  return async function execute(decision, text) {
    const supported =
      decision.route === "quick_ai" ||
      decision.route === "deep_ai" ||
      decision.route === "current_info";

    if (!supported) return null;

    if (!apiKey) {
      return {
        enabled: false,
        reason: "openrouter_not_configured"
      };
    }

    if (decision.route === "current_info" && !allowWebSearch) {
      return {
        enabled: false,
        reason: "web_search_not_enabled"
      };
    }

    const primaryModel = decision.route === "deep_ai" ? deepModel : fastModel;
    const models = uniqueModels([primaryModel, ...fallbacks]);

    const request = {
      models,
      provider: {
        sort: "latency",
        preferred_max_latency: { p90: 3 },
        allow_fallbacks: true
      },
      messages: [
        {
          role: "system",
          content:
            "Je bent Raise AI, een snelle persoonlijke smartwatch-assistent. " +
            "Antwoord in de taal van de gebruiker. Houd antwoorden standaard kort, duidelijk en direct bruikbaar op een horloge."
        },
        {
          role: "user",
          content: text
        }
      ],
      max_tokens: decision.route === "deep_ai" ? 320 : 180
    };

    if (decision.route === "current_info") {
      request.tools = [{ type: "openrouter:web_search" }];
    }

    let lastError = null;

    for (let attempt = 1; attempt <= attempts; attempt += 1) {
      try {
        const response = await fetchImpl(API_URL, {
          method: "POST",
          headers: {
            authorization: "Bearer " + apiKey,
            "content-type": "application/json",
            "x-title": "Raise AI"
          },
          body: JSON.stringify(request),
          signal: AbortSignal.timeout(9_000)
        });

        const body = await response.json().catch(() => ({}));

        if (!response.ok) {
          const error = new Error("openrouter_http_" + response.status);
          error.statusCode = 502;
          lastError = error;

          if (attempt < attempts && isRetryableStatus(response.status)) {
            await sleepImpl(retryDelayMs * attempt);
            continue;
          }

          throw error;
        }

        const answer = outputText(body);
        if (!answer) {
          const error = new Error("openrouter_empty_response");
          error.statusCode = 502;
          throw error;
        }

        return {
          enabled: true,
          provider: "openrouter",
          model: body.model ?? primaryModel,
          requestedModels: models,
          answer
        };
      } catch (error) {
        lastError = error;

        if (attempt < attempts && isRetryableThrownError(error)) {
          await sleepImpl(retryDelayMs * attempt);
          continue;
        }

        throw error;
      }
    }

    throw lastError ?? new Error("openrouter_request_failed");
  };
}
