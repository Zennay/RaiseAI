const DEFAULT_MAX_BODY_BYTES = 16 * 1024;

function normalizeContentType(value) {
  if (typeof value !== "string") return null;
  const parts = value.split(";").map(part => part.trim());
  if (parts[0]?.toLowerCase() !== "application/json") return null;

  if (parts.length === 1) return "application/json";
  if (parts.length !== 2) return null;

  const match = /^charset\s*=\s*(?:"utf-8"|utf-8)$/i.exec(parts[1]);
  return match ? "application/json; charset=utf-8" : null;
}

export function isReadinessJsonContentType(value) {
  return normalizeContentType(value) !== null;
}

export async function readReadinessJson(
  response,
  { maxBodyBytes = DEFAULT_MAX_BODY_BYTES } = {}
) {
  if (!Number.isSafeInteger(maxBodyBytes) || maxBodyBytes <= 0) {
    throw new TypeError("maxBodyBytes must be a positive safe integer");
  }

  if (!isReadinessJsonContentType(response?.headers?.["content-type"])) {
    response?.resume?.();
    throw new Error("health_response_not_json");
  }

  const chunks = [];
  let size = 0;

  for await (const chunk of response) {
    const bytes = Buffer.isBuffer(chunk) ? chunk : Buffer.from(chunk);
    size += bytes.length;

    if (size > maxBodyBytes) {
      response?.destroy?.();
      throw new Error("health_response_too_large");
    }

    chunks.push(bytes);
  }

  let decoded;
  try {
    decoded = new TextDecoder("utf-8", { fatal: true }).decode(
      Buffer.concat(chunks)
    );
  } catch {
    throw new Error("health_response_invalid_utf8");
  }

  try {
    return JSON.parse(decoded);
  } catch {
    throw new Error("health_response_invalid_json");
  }
}
