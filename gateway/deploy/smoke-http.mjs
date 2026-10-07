export const MAX_SMOKE_BODY_BYTES = 64 * 1024;

function destroyReadable(readable) {
  try {
    readable?.destroy?.();
  } catch {
    // Best-effort cleanup only; the body validation failure remains authoritative.
  }
}

export async function readSmokeResponseBody(
  readable,
  { parseJson = true, maxBytes = MAX_SMOKE_BODY_BYTES } = {}
) {
  if (!Number.isSafeInteger(maxBytes) || maxBytes < 1) {
    throw new TypeError("smoke maxBytes must be a positive safe integer");
  }

  const contentLength = readable?.headers?.["content-length"];
  let declaredBytes = null;

  if (contentLength !== undefined && contentLength !== null) {
    if (
      typeof contentLength !== "string" ||
      !/^\d+$/u.test(contentLength.trim())
    ) {
      destroyReadable(readable);
      return { json: null, bodyError: "smoke_content_length_invalid" };
    }

    declaredBytes = Number(contentLength.trim());
    if (!Number.isSafeInteger(declaredBytes) || declaredBytes > maxBytes) {
      destroyReadable(readable);
      return { json: null, bodyError: "smoke_body_too_large" };
    }
  }

  let totalBytes = 0;
  const chunks = [];

  try {
    for await (const chunk of readable) {
      const buffer = Buffer.isBuffer(chunk) ? chunk : Buffer.from(chunk);
      totalBytes += buffer.length;
      if (totalBytes > maxBytes) {
        destroyReadable(readable);
        return { json: null, bodyError: "smoke_body_too_large" };
      }
      chunks.push(buffer);
    }
  } catch {
    destroyReadable(readable);
    return { json: null, bodyError: "smoke_body_read_failed" };
  }

  if (declaredBytes !== null && totalBytes !== declaredBytes) {
    return { json: null, bodyError: "smoke_content_length_mismatch" };
  }

  if (!parseJson) {
    return { json: null, bodyError: null };
  }

  try {
    const text = new TextDecoder("utf-8", { fatal: true }).decode(
      Buffer.concat(chunks)
    );
    return { json: JSON.parse(text), bodyError: null };
  } catch {
    return { json: null, bodyError: "smoke_body_invalid_json" };
  }
}
