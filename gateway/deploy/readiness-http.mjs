import { evaluateReadinessResponse } from "./readiness-policy.mjs";

export function hasJsonMediaType(value) {
  if (typeof value !== "string") return false;
  return value.split(";", 1)[0].trim().toLowerCase() === "application/json";
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
