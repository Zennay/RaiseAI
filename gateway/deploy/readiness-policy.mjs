export function evaluateReadinessResponse({
  status,
  json,
  expectedRevision
}) {
  if (status !== 200) {
    return {
      ok: false,
      reason: `health_http_${status ?? "unknown"}`,
      revision: json?.revision ?? null
    };
  }

  if (json?.ok !== true) {
    return {
      ok: false,
      reason: "health_not_ok",
      revision: json?.revision ?? null
    };
  }

  const revision =
    typeof json?.revision === "string" && json.revision ? json.revision : null;

  if (!revision) {
    return {
      ok: false,
      reason: "health_revision_missing",
      revision: null
    };
  }

  if (revision !== expectedRevision) {
    return {
      ok: false,
      reason: "health_revision_mismatch",
      revision
    };
  }

  return {
    ok: true,
    reason: "ready",
    revision
  };
}
