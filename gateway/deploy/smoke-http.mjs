export const MAX_SMOKE_BODY_BYTES = 64 * 1024;
export const SMOKE_REQUEST_DEADLINE_MS = 10_000;

export function armSmokeRequestDeadline(
  request,
  {
    timeoutMs = SMOKE_REQUEST_DEADLINE_MS,
    setTimeoutImpl = globalThis.setTimeout,
    clearTimeoutImpl = globalThis.clearTimeout
  } = {}
) {
  if (!request || typeof request.destroy !== "function") {
    throw new TypeError("smoke request must expose destroy()");
  }
  if (!Number.isSafeInteger(timeoutMs) || timeoutMs < 1) {
    throw new TypeError("smoke request timeout must be a positive safe integer");
  }
  if (
    typeof setTimeoutImpl !== "function" ||
    typeof clearTimeoutImpl !== "function"
  ) {
    throw new TypeError("smoke request timer functions must be callable");
  }

  let active = true;
  const timer = setTimeoutImpl(() => {
    if (!active) return;
    active = false;
    request.destroy(new Error("smoke_request_deadline_exceeded"));
  }, timeoutMs);

  return function cancelSmokeRequestDeadline() {
    if (!active) return;
    active = false;
    try {
      clearTimeoutImpl(timer);
    } catch {
      // Timer cleanup is best effort after the request has already settled.
    }
  };
}

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
