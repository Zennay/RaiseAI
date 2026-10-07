import { evaluateReadinessResponse } from "./readiness-policy.mjs";

export const MAX_READINESS_BODY_BYTES = 64 * 1024;
export const MAX_READINESS_REQUEST_MS = 5_000;

export function readinessRequestBudget(remainingMs) {
  if (!Number.isSafeInteger(remainingMs) || remainingMs < 1) {
    throw new TypeError(
      "readiness remaining budget must be a positive safe integer"
    );
  }

  return Math.min(MAX_READINESS_REQUEST_MS, remainingMs);
}

export function armReadinessRequestDeadline(
  request,
  {
    timeoutMs = MAX_READINESS_REQUEST_MS,
    setTimeoutImpl = globalThis.setTimeout,
    clearTimeoutImpl = globalThis.clearTimeout
  } = {}
) {
  if (!request || typeof request.destroy !== "function") {
    throw new TypeError("readiness request must expose destroy()");
  }
  if (!Number.isSafeInteger(timeoutMs) || timeoutMs < 1) {
    throw new TypeError(
      "readiness request timeout must be a positive safe integer"
    );
  }
  if (
    typeof setTimeoutImpl !== "function" ||
    typeof clearTimeoutImpl !== "function"
  ) {
    throw new TypeError("readiness request timer functions must be callable");
  }

  let active = true;
  const timer = setTimeoutImpl(() => {
    if (!active) return;
    active = false;
    request.destroy(new Error("readiness_request_deadline_exceeded"));
  }, timeoutMs);

  return function cancelReadinessRequestDeadline() {
    if (!active) return;
    active = false;
    try {
      clearTimeoutImpl(timer);
    } catch {
      // Best-effort cleanup only after the request has already settled.
    }
  };
}

export async function readReadinessJson(
  readable,
  { maxBytes = MAX_READINESS_BODY_BYTES } = {}
) {
  if (!Number.isSafeInteger(maxBytes) || maxBytes < 1) {
    throw new TypeError("readiness maxBytes must be a positive safe integer");
  }

  const contentLength = readable?.headers?.["content-length"];
  let declaredBytes = null;

  if (contentLength !== undefined && contentLength !== null) {
    if (
      typeof contentLength !== "string" ||
      !/^\d+$/u.test(contentLength.trim())
    ) {
      return {
        json: null,
        bodyError: "health_content_length_invalid"
      };
    }

    declaredBytes = Number(contentLength.trim());
    if (!Number.isSafeInteger(declaredBytes) || declaredBytes > maxBytes) {
      return {
        json: null,
        bodyError: "health_body_too_large"
      };
    }
  }

  let totalBytes = 0;
  const chunks = [];

  for await (const chunk of readable) {
    const buffer = Buffer.isBuffer(chunk) ? chunk : Buffer.from(chunk);
    totalBytes += buffer.length;
    if (totalBytes > maxBytes) {
      return {
        json: null,
        bodyError: "health_body_too_large"
      };
    }
    chunks.push(buffer);
  }

  if (declaredBytes !== null && totalBytes !== declaredBytes) {
    return {
      json: null,
      bodyError: "health_content_length_mismatch"
    };
  }

  try {
    const text = new TextDecoder("utf-8", { fatal: true }).decode(
      Buffer.concat(chunks)
    );
    return {
      json: JSON.parse(text),
      bodyError: null
    };
  } catch {
    return {
      json: null,
      bodyError: "health_body_invalid_json"
    };
  }
}

export function hasJsonMediaType(value) {
  if (typeof value !== "string") return false;

  const parts = value.split(";").map(part => part.trim());
  if (parts[0]?.toLowerCase() !== "application/json") return false;
  if (parts.length === 1) return true;
  if (parts.length !== 2) return false;

  return /^charset\s*=\s*(?:"utf-8"|utf-8)$/iu.test(parts[1]);
}

export function evaluateReadinessHttpResponse({
  status,
  json,
  contentType,
  expectedRevision,
  bodyError = null
}) {
  if (!hasJsonMediaType(contentType)) {
    return {
      ok: false,
      reason: "health_media_type_invalid",
      revision: null
    };
  }

  if (bodyError) {
    return {
      ok: false,
      reason: bodyError,
      revision: null
    };
  }

  return evaluateReadinessResponse({
    status,
    json,
    expectedRevision
  });
}
