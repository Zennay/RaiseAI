const API_URL = "https://api.openai.com/v1/responses";
const REQUEST_BUDGET_MS = 7_000;
const MAX_RESPONSE_BODY_BYTES = 64 * 1024;
const MAX_MODEL_NAME_LENGTH = 256;

function hasUsableApiKey(value) {
  return (
    typeof value === "string" &&
    value.length > 0 &&
    !/[\s\u0000-\u001f\u007f]/u.test(value)
  );
}

function normalizeModelName(value) {
  if (typeof value !== "string") return null;
  const model = value.trim();
  if (
    !model ||
    model.length > MAX_MODEL_NAME_LENGTH ||
    /[\s\u0000-\u001f\u007f]/u.test(model)
  ) {
    return null;
  }
  return model;
}

function responseModelMatchesRequest(responseModel, requestedModel) {
  if (responseModel === requestedModel) return true;

  const snapshotPrefix = requestedModel + "-";
  if (!responseModel.startsWith(snapshotPrefix)) return false;

  const snapshotSuffix = responseModel.slice(snapshotPrefix.length);
  return /^\d{4}-\d{2}-\d{2}$/u.test(snapshotSuffix);
}

function upstreamFailure(message, cause) {
  const error = new Error(message, { cause });
  error.statusCode = 502;
  return error;
}

function hasJsonResponseType(response) {
  const value = response?.headers?.get?.("content-type");
  if (typeof value !== "string") return false;

  const parts = value.split(";").map(part => part.trim());
  if (parts[0]?.toLowerCase() !== "application/json") return false;
  if (parts.length === 1) return true;
  if (parts.length !== 2) return false;

  return /^charset\s*=\s*(?:"utf-8"|utf-8)$/iu.test(parts[1]);
}

async function cancelResponseBody(response) {
  try {
    await response?.body?.cancel?.();
  } catch {
    // Best-effort resource release; the provider failure remains authoritative.
  }
}

async function readBoundedJsonResponse(response) {
  const contentLength = response?.headers?.get?.("content-length");
  let declaredLength = null;

  if (contentLength !== null && contentLength !== undefined) {
    if (typeof contentLength !== "string") {
      await cancelResponseBody(response);
      return { ok: false, json: null };
    }

    const normalized = contentLength.trim();
    if (!/^\d+$/u.test(normalized)) {
      await cancelResponseBody(response);
      return { ok: false, json: null };
    }

    declaredLength = Number(normalized);
    if (
      !Number.isSafeInteger(declaredLength) ||
      declaredLength > MAX_RESPONSE_BODY_BYTES
    ) {
      await cancelResponseBody(response);
      return { ok: false, json: null };
    }
  }

  const reader = response?.body?.getReader?.();

  // Injected unit-test transports historically expose json() without a Fetch
  // ReadableStream. Production globalThis.fetch responses use the streaming
  // branch below, which enforces the byte budget before JSON parsing.
  if (!reader) {
    if (typeof response?.json !== "function") {
      return { ok: false, json: null };
    }

    try {
      const json = await response.json();
      const encoded = Buffer.from(JSON.stringify(json), "utf8");
      if (
        encoded.length > MAX_RESPONSE_BODY_BYTES ||
        (declaredLength !== null && declaredLength !== encoded.length)
      ) {
        return { ok: false, json: null };
      }
      return { ok: true, json };
    } catch {
      return { ok: false, json: null };
    }
  }

  const chunks = [];
  let totalBytes = 0;

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      if (!(value instanceof Uint8Array)) {
        await reader.cancel().catch(() => {});
        return { ok: false, json: null };
      }

      totalBytes += value.byteLength;
      if (totalBytes > MAX_RESPONSE_BODY_BYTES) {
        await reader.cancel().catch(() => {});
        return { ok: false, json: null };
      }
      chunks.push(value);
    }
  } catch {
    await reader.cancel().catch(() => {});
    return { ok: false, json: null };
  }

  if (declaredLength !== null && declaredLength !== totalBytes) {
    return { ok: false, json: null };
  }

  const bytes = new Uint8Array(totalBytes);
  let offset = 0;
  for (const chunk of chunks) {
    bytes.set(chunk, offset);
    offset += chunk.byteLength;
  }

  try {
    const text = new TextDecoder("utf-8", { fatal: true }).decode(bytes);
    return { ok: true, json: JSON.parse(text) };
  } catch {
    return { ok: false, json: null };
  }
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
        signal: AbortSignal.timeout(REQUEST_BUDGET_MS)
      });
    } catch (cause) {
      throw upstreamFailure("openai_request_failed", cause);
    }

    if (!response.ok) {
      await cancelResponseBody(response);
      const error = new Error("openai_http_" + response.status);
      error.statusCode = 502;
      throw error;
    }

    if (!hasJsonResponseType(response)) {
      await cancelResponseBody(response);
      const error = new Error("openai_invalid_response");
      error.statusCode = 502;
      throw error;
    }

    const parsedBody = await readBoundedJsonResponse(response);
    if (!parsedBody.ok) {
      const error = new Error("openai_invalid_response");
      error.statusCode = 502;
      throw error;
    }

    const body = parsedBody.json;
    const answer = outputText(body);
    if (!answer) {
      const error = new Error("openai_empty_response");
      error.statusCode = 502;
      throw error;
    }

    const responseModel =
      body?.model === undefined || body?.model === null
        ? model
        : normalizeModelName(body.model);
    if (!responseModel || !responseModelMatchesRequest(responseModel, model)) {
      const error = new Error("openai_invalid_response");
      error.statusCode = 502;
      throw error;
    }

    return {
      enabled: true,
      provider: "openai",
      model: responseModel,
      answer
    };
  };
}