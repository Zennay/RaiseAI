const MAX_BRIDGE_RESPONSE_BYTES = 4 * 1024;
const BRIDGE_DEADLINE_MS = 2_500;
const DEVICE_ID = /^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$/u;
const ROOMS = new Set(["woonkamer", "slaapkamer", "keuken"]);
const EXACT_LIGHT_COMMAND = /^(?:zet\s+)?(?:de\s+)?lamp(?:en)?\s+in\s+de\s+(woonkamer|slaapkamer|keuken)\s+(aan|uit)[.!]?$/iu;

function disabled(reason, answer) {
  return { enabled: false, provider: "google_home", reason, answer };
}

function bridgeOrigin(value) {
  if (
    typeof value !== "string" ||
    !/^(?:https:\/\/[^/?#\s]+|http:\/\/127\.0\.0\.1(?::\d{1,5})?)\/?$/iu.test(value)
  ) return null;

  try {
    const url = new URL(value);
    if (
      url.username || url.password || url.search || url.hash ||
      url.pathname !== "/" ||
      (url.protocol !== "https:" &&
        !(url.protocol === "http:" && url.hostname === "127.0.0.1"))
    ) return null;
    return url.origin;
  } catch {
    return null;
  }
}

function parseDevices(raw) {
  if (typeof raw !== "string" || !raw || raw.length > 1024) return null;
  try {
    const entries = JSON.parse(raw);
    if (!entries || typeof entries !== "object" || Array.isArray(entries)) return null;
    const keys = Object.keys(entries);
    if (keys.length < 1 || keys.length > ROOMS.size) return null;
    if (!keys.every(room => ROOMS.has(room) && DEVICE_ID.test(entries[room]))) return null;
    if (new Set(Object.values(entries)).size !== keys.length) return null;
    return entries;
  } catch {
    return null;
  }
}

function parseLightCommand(text) {
  if (typeof text !== "string" || text.length > 140) return null;
  const match = text.trim().match(EXACT_LIGHT_COMMAND);
  if (!match) return null;
  return {
    room: match[1].toLowerCase(),
    action: match[2].toLowerCase() === "aan" ? "turn_on" : "turn_off"
  };
}

async function readAcknowledgement(response) {
  const mediaType = response.headers?.get?.("content-type") ?? "";
  if (!/^application\/json(?:\s*;\s*charset\s*=\s*(?:utf-8|"utf-8"))?\s*$/iu.test(mediaType)) {
    await response.body?.cancel?.().catch(() => {});
    return null;
  }

  const declared = response.headers.get("content-length");
  if (declared !== null &&
      (!/^\d+$/u.test(declared) || Number(declared) > MAX_BRIDGE_RESPONSE_BYTES)) {
    await response.body?.cancel?.().catch(() => {});
    return null;
  }

  const reader = response.body?.getReader?.();
  if (!reader) return null;
  let size = 0;
  const chunks = [];
  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      if (!(value instanceof Uint8Array)) {
        await reader.cancel().catch(() => {});
        return null;
      }
      size += value.byteLength;
      if (size > MAX_BRIDGE_RESPONSE_BYTES) {
        await reader.cancel().catch(() => {});
        return null;
      }
      chunks.push(value);
    }
    if (declared !== null && Number(declared) !== size) return null;
    const bytes = new Uint8Array(size);
    let offset = 0;
    for (const part of chunks) {
      bytes.set(part, offset);
      offset += part.byteLength;
    }
    const value = JSON.parse(new TextDecoder("utf-8", { fatal: true }).decode(bytes));
    return value && typeof value === "object" && !Array.isArray(value) ? value : null;
  } catch {
    await reader.cancel().catch(() => {});
    return null;
  }
}

/**
 * Minimal private Home bridge contract:
 * POST /v1/light-actions {device_id,action} -> 200/202
 * {ok:true,status:"accepted",device_id,action}.
 *
 * The Watch never supplies a device ID, URL, token or arbitrary payload.
 * The configured bridge is responsible for upstream Google Home authorization.
 */
export function createHomeExecutor({
  enabled = false,
  origin = "",
  token = "",
  devicesJson = "",
  fetchImpl = globalThis.fetch
} = {}) {
  const endpoint = bridgeOrigin(origin);
  const devices = parseDevices(devicesJson);
  const validToken = typeof token === "string" && token.length >= 32 &&
    token.length <= 256 && !/[\s\u0000-\u001f\u007f]/u.test(token);

  return async function execute(decision, text) {
    if (decision?.route !== "smart_home") return null;

    // Never grant a side-effect to a future route with a different contract.
    if (decision.target !== "home.command" || decision.connector !== "google_home") {
      return disabled("home_route_invalid", "De Home-opdracht is niet herkend.");
    }
    if (!enabled) {
      return disabled("home_not_enabled", "Home-bediening is nog niet ingeschakeld.");
    }
    if (!endpoint || !devices || !validToken || typeof fetchImpl !== "function") {
      return disabled("home_config_invalid", "Home-bediening is niet veilig geconfigureerd.");
    }

    const command = parseLightCommand(text);
    if (!command) {
      return disabled("home_command_unsupported", "Alleen een expliciete aan- of uitopdracht voor lampen in één ingestelde kamer wordt ondersteund.");
    }
    const deviceId = devices[command.room];
    if (!deviceId) {
      return disabled("home_device_not_allowed", "Deze kamer is niet vrijgegeven voor Home-bediening.");
    }

    try {
      const response = await fetchImpl(endpoint + "/v1/light-actions", {
        method: "POST",
        headers: {
          authorization: "Bearer " + token,
          "content-type": "application/json"
        },
        body: JSON.stringify({ device_id: deviceId, action: command.action }),
        redirect: "error",
        signal: AbortSignal.timeout(BRIDGE_DEADLINE_MS)
      });

      if (response.status === 401 || response.status === 403) {
        await response.body?.cancel?.().catch(() => {});
        return disabled("home_bridge_unauthorized", "De Home-bridge weigert de toestemming.");
      }
      if (!response.ok) {
        await response.body?.cancel?.().catch(() => {});
        return disabled("home_bridge_rejected", "De Home-bridge heeft de opdracht niet geaccepteerd.");
      }

      const ack = await readAcknowledgement(response);
      if (
        !ack || ack.ok !== true || ack.status !== "accepted" ||
        ack.device_id !== deviceId || ack.action !== command.action
      ) {
        return disabled("home_bridge_invalid_ack", "De Home-bridge gaf geen geldige bevestiging.");
      }

      return {
        enabled: true,
        provider: "google_home",
        reason: "home_command_accepted",
        answer: "De opdracht voor de lampen in de " + command.room +
          " is ontvangen. De apparaatstatus is nog niet geverifieerd."
      };
    } catch {
      return disabled("home_bridge_unavailable", "De Home-bridge is tijdelijk niet bereikbaar.");
    }
  };
}
