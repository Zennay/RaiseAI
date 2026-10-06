import { evaluateReadinessResponse } from "./readiness-policy.mjs";

export const MAX_READINESS_BODY_BYTES = 64 * 1024;

export async function readReadinessJson(
  readable,
  { maxBytes = MAX_READINESS_BODY_BYTES } = {}
) {
  if (!Number.isSafeInteger(maxBytes) || maxBytes < 1) {
    throw new TypeError("readiness maxBytes must be a positive safe integer");
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
