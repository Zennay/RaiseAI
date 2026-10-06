import { evaluateReadinessResponse } from "./readiness-policy.mjs";

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
  expectedRevision
}) {
  if (!hasJsonMediaType(contentType)) {
    return {
      ok: false,
      reason: "health_media_type_invalid",
      revision: null
    };
  }

  return evaluateReadinessResponse({
    status,
    json,
    expectedRevision
  });
}
