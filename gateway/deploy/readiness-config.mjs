export function positiveInteger(value, fallback) {
  if (!Number.isSafeInteger(fallback) || fallback <= 0) {
    throw new TypeError("fallback must be a positive safe integer");
  }

  const text = String(value ?? "").trim();
  if (!/^\d+$/.test(text)) return fallback;

  const parsed = Number(text);
  return Number.isSafeInteger(parsed) && parsed > 0 ? parsed : fallback;
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
