export function evaluateZCloudProbe({
  status,
  json,
  requireZCloud = false
}) {
  if (status !== 200) {
    return {
      ok: false,
      degraded: false,
      reason: `zcloud_http_${status ?? "unknown"}`
    };
  }

  if (json?.route !== "zcloud_task") {
    return {
      ok: false,
      degraded: false,
      reason: `unexpected_route_${json?.route ?? "missing"}`
    };
  }

  const provider = json?.execution?.provider ?? null;
  const reason = json?.execution?.reason ?? null;

  if (provider !== "zcloud") {
    return {
      ok: false,
      degraded: false,
      reason: "unexpected_provider"
    };
  }

  if (reason === "zcloud_custom_task_not_supported") {
    return {
      ok: true,
      degraded: false,
      reason
    };
  }

  if (reason === "zcloud_unavailable") {
    return {
      ok: !requireZCloud,
      degraded: true,
      reason
    };
  }

  return {
    ok: false,
    degraded: false,
    reason: reason ?? "unexpected_zcloud_result"
  };
}
