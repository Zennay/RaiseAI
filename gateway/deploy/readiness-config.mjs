const MAX_TIMER_DELAY_MS = 2_147_483_647;

export function canonicalDeployRevision(
  value,
  label = "expected deploy revision"
) {
  if (
    typeof value !== "string" ||
    !/^(?:[0-9a-f]{40}|[0-9a-f]{64})$/u.test(value)
  ) {
    throw new TypeError(
      `${label} must be a canonical 40/64-character lowercase Git revision`
    );
  }

  return value;
}

export function positiveInteger(value, fallback) {
  if (
    !Number.isSafeInteger(fallback) ||
    fallback <= 0 ||
    fallback > MAX_TIMER_DELAY_MS
  ) {
    throw new TypeError("fallback must be a positive timer-safe integer");
  }

  const text = String(value ?? "").trim();
  if (!/^\d+$/.test(text)) return fallback;

  const parsed = Number(text);
  return Number.isSafeInteger(parsed) &&
    parsed > 0 &&
    parsed <= MAX_TIMER_DELAY_MS
    ? parsed
    : fallback;
}

export function httpsOrigin(value, label = "gateway URL") {
  if (
    typeof value !== "string" ||
    !value ||
    /[\u0000-\u0020\u007f]/u.test(value)
  ) {
    throw new TypeError(`${label} must be a valid HTTPS origin`);
  }

  let url;
  try {
    url = new URL(value);
  } catch {
    throw new TypeError(`${label} must be a valid HTTPS origin`);
  }

  if (
    url.protocol !== "https:" ||
    !url.hostname ||
    url.username ||
    url.password ||
    (url.pathname !== "/" && url.pathname !== "") ||
    url.search ||
    url.hash
  ) {
    throw new TypeError(`${label} must be a valid HTTPS origin`);
  }

  return url;
}
