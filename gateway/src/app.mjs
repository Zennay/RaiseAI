import crypto from "node:crypto";
import { classifyIntent } from "./router.mjs";

const MAX_BODY = 16 * 1024;
const MAX_TEXT = 4000;
const MAX_EXECUTION_TOKEN_CHARS = 256;
const MAX_ANSWER_TEXT_CHARS = 4096;
const REQUESTS_PER_MINUTE = 120;
const MAX_RATE_LIMIT_BUCKETS = 1024;

function json(res, status, body) {
  const payload = Buffer.from(JSON.stringify(body));
  res.writeHead(status, {
    "content-type": "application/json; charset=utf-8",
    "content-length": payload.length,
    "cache-control": "no-store"
  });
  res.end(payload);
}

function safeTokenEqual(actual, expected) {
  if (!actual || !expected) return false;
  const a = Buffer.from(actual);
  const b = Buffer.from(expected);
  return a.length === b.length && crypto.timingSafeEqual(a, b);
}

function bearer(req) {
  const value = req.headers.authorization ?? "";
  return value.startsWith("Bearer ") ? value.slice(7) : "";
}

function hasJsonContentType(req) {
  const value = req.headers["content-type"];
  if (typeof value !== "string") return false;
  return value.split(";", 1)[0].trim().toLowerCase() === "application/json";
}

function isCanonicalExecutionToken(value) {
  return (
    typeof value === "string" &&
    value.length > 0 &&
    !/[\s\u0000-\u001f\u007f]/u.test(value)
  );
}

function normalizeExecutionResult(result) {
  if (result === null || result === undefined) {
    return {
      enabled: false,
      reason: "connector_not_configured",
      provider: null,
      model: null,
      answer: null
    };
  }

  if (typeof result !== "object" || Array.isArray(result)) {
    const err = new Error("invalid_execution_result");
    err.statusCode = 502;
    throw err;
  }

  if (typeof result.enabled !== "boolean") {
    const err = new Error("invalid_execution_result");
    err.statusCode = 502;
    throw err;
  }

  for (const field of ["reason", "provider", "model"]) {
    if (
      result[field] !== undefined &&
      result[field] !== null &&
      !isCanonicalExecutionToken(result[field])
    ) {
      const err = new Error("invalid_execution_result");
      err.statusCode = 502;
      throw err;
    }
  }

  if (
    result.answer !== undefined &&
    result.answer !== null &&
    typeof result.answer !== "string"
  ) {
    const err = new Error("invalid_execution_result");
    err.statusCode = 502;
    throw err;
  }

  if (
    typeof result.answer === "string" &&
    (!result.answer.trim() || result.answer.length > MAX_ANSWER_TEXT_CHARS)
  ) {
    const err = new Error("invalid_execution_result");
    err.statusCode = 502;
    throw err;
  }

  return {
    enabled: result.enabled,
    reason: result.reason ?? null,
    provider: result.provider ?? null,
    model: result.model ?? null,
    answer: result.answer ?? null
  };
}

function safeErrorStatus(error) {
  const status = error?.statusCode;
  return Number.isInteger(status) && status >= 400 && status <= 599
    ? status
    : 500;
}

export function createRateLimiter({
  requestsPerMinute = REQUESTS_PER_MINUTE,
  maxBuckets = MAX_RATE_LIMIT_BUCKETS
} = {}) {
  if (
    !Number.isSafeInteger(requestsPerMinute) ||
    requestsPerMinute < 1 ||
    !Number.isSafeInteger(maxBuckets) ||
    maxBuckets < 1
  ) {
    throw new Error("invalid_rate_limit_config");
  }

  const buckets = new Map();
  let activeMinute = null;

  return {
    allow(clientKey, minute) {
      if (!Number.isSafeInteger(minute)) return false;

      if (activeMinute !== minute) {
        buckets.clear();
        activeMinute = minute;
      }

      const key =
        typeof clientKey === "string" && clientKey.length > 0
          ? clientKey
          : "unknown";
      const count = buckets.get(key);

      if (count === undefined) {
        if (buckets.size >= maxBuckets) return false;
        buckets.set(key, 1);
        return true;
      }

      if (count >= requestsPerMinute) return false;
      buckets.set(key, count + 1);
      return true;
    }
  };
}

async function readJson(req) {
  let size = 0;
  const chunks = [];

  for await (const chunk of req) {
    size += chunk.length;
    if (size > MAX_BODY) {
      const err = new Error("payload_too_large");
      err.statusCode = 413;
      throw err;
    }
    chunks.push(chunk);
  }

  try {
    const decoded = new TextDecoder("utf-8", { fatal: true }).decode(
      Buffer.concat(chunks)
    );
    return JSON.parse(decoded || "{}");
  } catch {
    const err = new Error("invalid_json");
    err.statusCode = 400;
    throw err;
  }
}

export function createHandler({
  token,
  execute = null,
  now = () => Date.now(),
  revision = "unknown"
}) {
  if (
    typeof token !== "string" ||
    token.length < 32 ||
    /[\s\u0000-\u001f\u007f]/u.test(token)
  ) {
    throw new Error(
      "RAISE_GATEWAY_TOKEN must be at least 32 characters with no whitespace or control characters"
    );
  }

  const rateLimiter = createRateLimiter();

  return async function handler(req, res) {
    const requestId = crypto.randomUUID();

    if (req.method === "GET" && req.url === "/health") {
      return json(res, 200, {
        ok: true,
        service: "raise-gateway",
        version: "0.1.0",
        revision
      });
    }

    if (
      req.method !== "POST" ||
      (req.url !== "/v1/route" && req.url !== "/v1/assistant")
    ) {
      return json(res, 404, { error: "not_found", requestId });
    }

    if (!safeTokenEqual(bearer(req), token)) {
      return json(res, 401, { error: "unauthorized", requestId });
    }

    if (!hasJsonContentType(req)) {
      return json(res, 415, { error: "unsupported_media_type", requestId });
    }

    const ip = req.socket.remoteAddress ?? "unknown";
    const minute = Math.floor(now() / 60000);

    if (!rateLimiter.allow(ip, minute)) {
      return json(res, 429, { error: "rate_limited", requestId });
    }

    try {
      const body = await readJson(req);

      if (body === null || typeof body !== "object" || Array.isArray(body)) {
        return json(res, 400, { error: "invalid_request", requestId });
      }

      if (body.text !== undefined && typeof body.text !== "string") {
        return json(res, 400, { error: "invalid_text", requestId });
      }

      const text = (body.text ?? "").trim();

      if (!text) {
        return json(res, 400, { error: "text_required", requestId });
      }

      if (text.length > MAX_TEXT) {
        return json(res, 413, { error: "text_too_long", requestId });
      }

      const decision = classifyIntent(text);
      const connectorResult = execute
        ? await execute(decision, text)
        : null;

      const execution = normalizeExecutionResult(connectorResult);
      const aiRoute =
        decision.route === "quick_ai" ||
        decision.route === "deep_ai" ||
        decision.route === "current_info";

      if (
        aiRoute &&
        execution.enabled &&
        (
          execution.answer === null ||
          typeof execution.provider !== "string" ||
          !execution.provider ||
          execution.provider !== execution.provider.trim() ||
          typeof execution.model !== "string" ||
          !execution.model ||
          execution.model !== execution.model.trim()
        )
      ) {
        const err = new Error("invalid_execution_result");
        err.statusCode = 502;
        throw err;
      }

      return json(res, 200, {
        requestId,
        status: execution.answer ? "answered" : "routed",
        ...decision,
        execution: {
          enabled: execution.enabled,
          reason: execution.reason,
          provider: execution.provider,
          model: execution.model
        },
        answer: execution.answer
      });
    } catch (error) {
      const errorMessage = error?.message;
      const publicError =
        errorMessage === "invalid_json" || errorMessage === "payload_too_large"
          ? errorMessage
          : "internal_error";

      return json(res, safeErrorStatus(error), {
        error: publicError,
        requestId
      });
    }
  };
}