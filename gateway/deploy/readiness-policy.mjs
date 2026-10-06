function revision(value) {
  const normalized = typeof value === "string" ? value.trim() : "";
  return /^[0-9a-f]{40}$/i.test(normalized) ? normalized : null;
}

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

  const expected = revision(expectedRevision);
  if (!expected) {
    return {
      ok: false,
      reason: "expected_revision_invalid",
      revision: json?.revision ?? null
    };
  }

  const liveRevision = revision(json?.revision);
  if (!liveRevision) {
    return {
      ok: false,
      reason:
        typeof json?.revision === "string" && json.revision.trim()
          ? "health_revision_invalid"
          : "health_revision_missing",
      revision: null
    };
  }

  if (liveRevision !== expected) {
    return {
      ok: false,
      reason: "health_revision_mismatch",
      revision: liveRevision
    };
  }

  return {
    ok: true,
    reason: "ready",
    revision: liveRevision
  };
}
