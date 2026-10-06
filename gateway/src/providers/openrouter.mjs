const API_URL = "https://openrouter.ai/api/v1/chat/completions";
const REQUEST_BUDGET_MS = 7_000;

function hasWhitespaceOrControl(value) {
  return /[\s\u0000-\u001f\u007f]/u.test(value);
}

function hasUsableApiKey(value) {
  return (
    typeof value === "string" &&
    value.length > 0 &&
    !hasWhitespaceOrControl(value)
  );
}

function upstreamFailure(message, cause) {
  const error = new Error(message, { cause });
  error.statusCode = 502;
  return error;
}

function parseFallbackModels(value) {
  return String(value ?? "")
    .split(",")
    .map((model) => model.trim())
    .filter(Boolean);
}

function normalizeModelName(value) {
  if (typeof value !== "string") return null;
  const model = value.trim();
  if (!model || hasWhitespaceOrControl(model)) return null;
  return model;
}

function normalizeFallbackModels(models) {
  const normalized = [];

  for (const value of models) {
    if (typeof value !== "string") return null;
    const model = value.trim();
    if (!model) continue;
    if (hasWhitespaceOrControl(model)) return null;
    normalized.push(model);
  }

  return [...new Set(normalized)];
}

function hasJsonResponseType(response) {
  const value = response?.headers?.get?.("content-type");
  if (typeof value !== "string") return false;
  return value.split(";", 1)[0].trim().toLowerCase() === "application/json";
}

function outputText(response) {
  if (
    response === null ||
    typeof response !== "object" ||
    Array.isArray(response) ||
    !Array.isArray(response.choices) ||
    response.choices.length !== 1
  ) {
    return null;
  }

  const firstChoice = response.choices[0];
  if (
    firstChoice === null ||
    typeof firstChoice !== "object" ||
    Array.isArray(firstChoice) ||
    firstChoice.message === null ||
    typeof firstChoice.message !== "object" ||
    Array.isArray(firstChoice.message) ||
    firstChoice.message.role !== "assistant"
  ) {
    return null;
  }

  const content = firstChoice.message.content;
  if (typeof content === "string") {
    const text = content.trim();
    return text || null;
  }

  if (Array.isArray(content)) {
    const validTextParts =
      content.length > 0 &&
      content.every(
        (part) =>
          part !== null &&
          typeof part === "object" &&
          !Array.isArray(part) &&
          part.type === "text" &&
          typeof part.text === "string"
      );
    if (!validTextParts) return null;

    const text = content
      .map((part) => part.text)
      .join("")
      .trim();
    return text || null;
  }

  return null;
}

function hasCompleteFinishReason(response) {
  const finishReason = response?.choices?.[0]?.finish_reason;
  return (
    finishReason === undefined ||
    finishReason === null ||
    finishReason === "stop"
  );
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
    : typeof fallbackModels === "string"
      ? parseFallbackModels(fallbackModels)
      : null;
  const attempts = Math.max(1, Math.min(Number(maxAttempts) || 1, 3));

  return async function execute(decision, text) {
    const supported =
      decision.route === "quick_ai" ||
      decision.route === "deep_ai" ||
      decision.route === "current_info";

    if (!supported) return null;

    if (!hasUsableApiKey(apiKey)) {
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

    const primaryModel = normalizeModelName(
      decision.route === "deep_ai" ? deepModel : fastModel
    );
    const normalizedFallbacks =
      fallbacks === null ? null : normalizeFallbackModels(fallbacks);

    if (!primaryModel || !normalizedFallbacks) {
      return {
        enabled: false,
        reason: "openrouter_model_config_invalid"
      };
    }

    const models = [...new Set([primaryModel, ...normalizedFallbacks])];

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
    // The Watch client gives the gateway 8 seconds to answer. Reuse one
    // deadline across retries so provider work cannot outlive that caller.
    const requestSignal = AbortSignal.timeout(REQUEST_BUDGET_MS);

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
          signal: requestSignal
        });

        const jsonMediaType = hasJsonResponseType(response);
        const body = jsonMediaType
          ? await response.json().catch(() => ({}))
          : {};

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

        if (!jsonMediaType) {
          const error = new Error("openrouter_invalid_response");
          error.statusCode = 502;
          throw error;
        }

        const answer = outputText(body);
        if (!answer) {
          const error = new Error("openrouter_empty_response");
          error.statusCode = 502;
          throw error;
        }

        if (!hasCompleteFinishReason(body)) {
          const error = new Error("openrouter_incomplete_response");
          error.statusCode = 502;
          throw error;
        }

        const responseModel =
          body.model === undefined || body.model === null
            ? primaryModel
            : normalizeModelName(body.model);
        if (!responseModel || !models.includes(responseModel)) {
          const error = new Error("openrouter_invalid_response");
          error.statusCode = 502;
          throw error;
        }

        return {
          enabled: true,
          provider: "openrouter",
          model: responseModel,
          requestedModels: models,
          answer
        };
      } catch (error) {
        lastError = error;

        if (attempt < attempts && isRetryableThrownError(error)) {
          await sleepImpl(retryDelayMs * attempt);
          continue;
        }

        if (
          error?.statusCode === 502 &&
          String(error?.message ?? "").startsWith("openrouter_")
        ) {
          throw error;
        }

        throw upstreamFailure("openrouter_request_failed", error);
      }
    }

    throw upstreamFailure("openrouter_request_failed", lastError);
  };
}
