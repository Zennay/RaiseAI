export function positiveInteger(value, fallback) {
  if (!Number.isSafeInteger(fallback) || fallback <= 0) {
    throw new TypeError("fallback must be a positive safe integer");
  }

  const text = String(value ?? "").trim();
  if (!/^\d+$/.test(text)) return fallback;

  const parsed = Number(text);
  return Number.isSafeInteger(parsed) && parsed > 0 ? parsed : fallback;
}
