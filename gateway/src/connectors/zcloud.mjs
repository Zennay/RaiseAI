const DEFAULT_BASE_URL = "http://127.0.0.1:8765";
const VALID_DESIRED_STATES = new Set(["running", "paused", "draining"]);
const PROJECT_ID = /^[a-z0-9][a-z0-9_-]{0,63}$/u;
const CONTROL_CHARS = /[\u0000-\u001f\u007f]/u;
const UNSAFE_DISPLAY_CHARS = /[\p{Cc}\p{Cf}]/u;
const MAX_TARGETS = 256;
const MAX_TARGET_NAME_LENGTH = 256;
const MAX_RESPONSE_BODY_BYTES = 64 * 1024;

function normalize(value) {
  return String(value ?? "")
    .normalize("NFKD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, " ")
    .trim()
    .replace(/\s+/g, " ");
}

function isLoopbackHost(hostname) {
  const host = String(hostname ?? "").toLowerCase();
  return (
    host === "localhost" ||
    host === "::1" ||
    host === "[::1]" ||
    /^127(?:\.\d{1,3}){3}$/u.test(host)
  );
}

function normalizeBaseUrl(value) {
  if (
    typeof value !== "string" ||
    !value ||
    value.trim() !== value ||
    /\s/u.test(value) ||
    CONTROL_CHARS.test(value)
  ) {
    throw new Error("zcloud_base_url_invalid");
  }

  let parsed;
  try {
    parsed = new URL(value);
  } catch {
    throw new Error("zcloud_base_url_invalid");
  }

  if (
    (parsed.protocol !== "http:" && parsed.protocol !== "https:") ||
    (parsed.protocol === "http:" && !isLoopbackHost(parsed.hostname)) ||
    parsed.username ||
    parsed.password ||
    (parsed.pathname !== "/" && parsed.pathname !== "") ||
    parsed.search ||
    parsed.hash
  ) {
    throw new Error("zcloud_base_url_invalid");
  }

  return parsed.origin;
}

function projectDisplayName(project) {
  const raw = typeof project.name === "string" ? project.name.trim() : "";
  if (!raw) return "";

  const allocated = raw.match(/^Portfolio Worker [1-9]\d*\/[1-9]\d*\s*·\s*(.+)$/i);
  if (allocated) return allocated[1].trim();

  const local = raw.match(/^(.+?)\s*·\s*worker [1-9]\d*\/[1-9]\d*$/i);
  if (local) return local[1].trim();

  if (/^Portfolio Worker\b/i.test(raw) || /·\s*worker\b/i.test(raw)) {
    return "";
  }

  return raw;
}

function canonicalAliasesForBase(baseProjectId) {
  const base = normalize(baseProjectId);
  const aliases = new Set();

  if (base) aliases.add(base);

  if (base === "raiseai") aliases.add("raise ai");
  if (base === "ulab") aliases.add("u lab");
  if (base === "lightup") aliases.add("light up");
  if (base === "cloud") {
    aliases.add("zcloud");
    aliases.add("z cloud");
  }
  if (base === "zssh") aliases.add("z ssh");
  if (base === "zguard") {
    aliases.add("z guard");
    aliases.add("zguard zbrowse");
  }
  if (base === "portfolio review") aliases.add("portfolio birdseye review");

  return aliases;
}

function displayNameMatchesBase(baseProjectId, displayName) {
  const name = normalize(displayName);
  return name && canonicalAliasesForBase(baseProjectId).has(name);
}

function aliasesFor(project) {
  const aliases = canonicalAliasesForBase(project.base_project_id);
  const name = normalize(projectDisplayName(project));

  if (name) aliases.add(name);

  return [...aliases].sort((a, b) => b.length - a.length);
}

function groupTargets(payload) {
  if (
    payload === null ||
    typeof payload !== "object" ||
    Array.isArray(payload) ||
    payload.projects === null ||
    typeof payload.projects !== "object" ||
    Array.isArray(payload.projects)
  ) {
    throw new Error("zcloud_targets_invalid");
  }

  const groups = new Map();
  let targetCount = 0;

  for (const [workerKey, target] of Object.entries(payload.projects)) {
    targetCount += 1;
    if (targetCount > MAX_TARGETS) {
      throw new Error("zcloud_targets_invalid");
    }
    if (target === null || typeof target !== "object" || Array.isArray(target)) {
      throw new Error("zcloud_targets_invalid");
    }
    if (
      typeof target.base_project_id !== "string" ||
      !PROJECT_ID.test(target.base_project_id) ||
      typeof target.project_id !== "string" ||
      target.project_id !== workerKey ||
      !Number.isSafeInteger(target.worker_slot) ||
      target.worker_slot < 1 ||
      !Number.isSafeInteger(target.worker_count) ||
      target.worker_count < 1 ||
      target.worker_slot > target.worker_count ||
      workerKey !== target.base_project_id + "::w" + target.worker_slot
    ) {
      throw new Error("zcloud_targets_invalid");
    }
    if (
      typeof target.active !== "boolean" ||
      typeof target.assignment_ready !== "boolean" ||
      typeof target.desired_state !== "string" ||
      !VALID_DESIRED_STATES.has(target.desired_state) ||
      (target.desired_state === "paused" && target.active) ||
      (target.active && !target.assignment_ready)
    ) {
      throw new Error("zcloud_targets_invalid");
    }
    if (
      target.name !== undefined &&
      target.name !== null &&
      (
        typeof target.name !== "string" ||
        target.name.length > MAX_TARGET_NAME_LENGTH ||
        target.name !== target.name.trim() ||
        UNSAFE_DISPLAY_CHARS.test(target.name)
      )
    ) {
      throw new Error("zcloud_targets_invalid");
    }

    const base = target.base_project_id;
    const displayName = projectDisplayName(target);
    const nameKey = displayName ? normalize(displayName) : null;
    if (
      target.name !== undefined &&
      target.name !== null &&
      (!nameKey || !displayNameMatchesBase(base, displayName))
    ) {
      throw new Error("zcloud_targets_invalid");
    }

    const current = groups.get(base) ?? {
      base_project_id: base,
      name: displayName || base,
      nameKey,
      active: false,
      aliases: new Set(),
      workerCount: target.worker_count,
      workerSlots: new Set()
    };

    if (
      current.workerCount !== target.worker_count ||
      current.workerSlots.has(target.worker_slot)
    ) {
      throw new Error("zcloud_targets_invalid");
    }
    if (nameKey && current.nameKey && current.nameKey !== nameKey) {
      throw new Error("zcloud_targets_invalid");
    }
    if (nameKey && !current.nameKey) {
      current.name = displayName;
      current.nameKey = nameKey;
    }

    current.active ||= target.active;
    current.workerSlots.add(target.worker_slot);
    for (const alias of aliasesFor(target)) current.aliases.add(alias);
    groups.set(base, current);
  }

  for (const group of groups.values()) {
    // Every slot is already proven unique and inside 1..workerCount. If the
    // cardinality matches workerCount, the set must therefore be complete;
    // do not linearly scan an untrusted worker_count value.
    if (group.workerSlots.size !== group.workerCount) {
      throw new Error("zcloud_targets_invalid");
    }
  }

  return [...groups.values()].map(
    ({ nameKey: _nameKey, workerCount: _workerCount, workerSlots: _workerSlots, ...group }) => ({
      ...group,
      aliases: [...group.aliases].sort((a, b) => b.length - a.length)
    })
  );
}

function findProject(text, projects) {
  const normalizedText = normalize(text);

  const candidates = [];
  for (const project of projects) {
    for (const alias of project.aliases) {
      const padded = " " + normalizedText + " ";
      if (padded.includes(" " + alias + " ")) {
        candidates.push({ project, alias });
      }
    }
  }

  candidates.sort((a, b) => b.alias.length - a.alias.length);
  if (candidates.length === 0) return null;

  const longestAliasLength = candidates[0].alias.length;
  const strongest = candidates.filter(candidate => candidate.alias.length === longestAliasLength);
  const projectIds = new Set(strongest.map(candidate => candidate.project.base_project_id));

  if (projectIds.size > 1) {
    return { ambiguous: true };
  }

  return strongest[0];
}

function genericForms(alias) {
  const prefixes = [
    "ga door met",
    "ga verder met",
    "werk verder met",
    "werk verder aan",
    "werk door met",
    "ga door",
    "ga verder",
    "werk verder",
    "push",
    "start"
  ];

  const forms = new Set();
  for (const prefix of prefixes) {
    forms.add(prefix + " " + alias);
    forms.add(prefix + " project " + alias);
    forms.add(prefix + " het project " + alias);
  }
  return forms;
}

export function isGenericContinuation(text, aliases) {
  let normalizedText = normalize(text);
  if (normalizedText.startsWith("even ")) {
    normalizedText = normalizedText.slice(5);
  }
  if (normalizedText.endsWith(" alsjeblieft")) {
    normalizedText = normalizedText.slice(0, -" alsjeblieft".length);
  }

  return aliases.some(alias => genericForms(alias).has(normalizedText));
}

function hasJsonResponseType(response) {
  const value = response?.headers?.get?.("content-type");
  if (typeof value !== "string") return false;

  const parts = value.split(";").map(part => part.trim());
  if (parts[0]?.toLowerCase() !== "application/json") return false;
  if (parts.length === 1) return true;
  if (parts.length !== 2) return false;

  return /^charset\s*=\s*(?:"utf-8"|utf-8)$/iu.test(parts[1]);
}

async function cancelResponseBody(response) {
  try {
    await response?.body?.cancel?.();
  } catch {
    // Best effort only; the caller is already rejecting this response.
  }
}

async function readBoundedJsonResponse(response) {
  const contentLength = response?.headers?.get?.("content-length");
  let declaredBytes = null;
  if (contentLength !== null && contentLength !== undefined) {
    if (typeof contentLength !== "string") {
      await cancelResponseBody(response);
      return { ok: false, json: null };
    }

    const normalized = contentLength.trim();
    if (!/^\d+$/u.test(normalized)) {
      await cancelResponseBody(response);
      return { ok: false, json: null };
    }

    declaredBytes = Number(normalized);
    if (
      !Number.isSafeInteger(declaredBytes) ||
      declaredBytes > MAX_RESPONSE_BODY_BYTES
    ) {
      await cancelResponseBody(response);
      return { ok: false, json: null };
    }
  }

  const reader = response?.body?.getReader?.();
  if (!reader) {
    return { ok: false, json: null };
  }

  const chunks = [];
  let totalBytes = 0;

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      if (!(value instanceof Uint8Array)) {
        await reader.cancel().catch(() => {});
        return { ok: false, json: null };
      }

      totalBytes += value.byteLength;
      if (totalBytes > MAX_RESPONSE_BODY_BYTES) {
        await reader.cancel().catch(() => {});
        return { ok: false, json: null };
      }
      chunks.push(value);
    }

    if (declaredBytes !== null && totalBytes !== declaredBytes) {
      return { ok: false, json: null };
    }

    const bytes = new Uint8Array(totalBytes);
    let offset = 0;
    for (const chunk of chunks) {
      bytes.set(chunk, offset);
      offset += chunk.byteLength;
    }

    const text = new TextDecoder("utf-8", { fatal: true }).decode(bytes);
    return { ok: true, json: JSON.parse(text) };
  } catch {
    await reader.cancel().catch(() => {});
    return { ok: false, json: null };
  }
}

async function jsonFetch(fetchImpl, url, options = {}) {
  const response = await fetchImpl(url, {
    ...options,
    signal: options.signal ?? AbortSignal.timeout(2_500)
  });

  const jsonMediaType = hasJsonResponseType(response);
  if (!response.ok || !jsonMediaType) {
    await cancelResponseBody(response);
    return { response, body: null, jsonMediaType };
  }

  const parsed = await readBoundedJsonResponse(response);
  return {
    response,
    body: parsed.ok ? parsed.json : null,
    jsonMediaType
  };
}

export function createZCloudExecutor({
  baseUrl = DEFAULT_BASE_URL,
  fetchImpl = globalThis.fetch
} = {}) {
  const root = normalizeBaseUrl(baseUrl);

  return async function execute(decision, text) {
    if (decision.route !== "zcloud_task") return null;

    let targets;
    try {
      const { response, body, jsonMediaType } = await jsonFetch(
        fetchImpl,
        root + "/api/runner-targets"
      );

      if (!response.ok) {
        return {
          enabled: false,
          provider: "zcloud",
          reason: "zcloud_targets_unavailable",
          answer: "zCloud is nu niet klaar om opdrachten te ontvangen."
        };
      }

      if (!jsonMediaType) {
        throw new Error("zcloud_targets_invalid");
      }

      targets = groupTargets(body);
    } catch (error) {
      if (error?.message === "zcloud_targets_invalid") {
        return {
          enabled: false,
          provider: "zcloud",
          reason: "zcloud_targets_invalid",
          answer: "zCloud stuurde ongeldige projectstatus terug."
        };
      }
      return {
        enabled: false,
        provider: "zcloud",
        reason: "zcloud_unavailable",
        answer: "zCloud is nu niet bereikbaar."
      };
    }

    const selected = findProject(text, targets);
    if (!selected) {
      return {
        enabled: false,
        provider: "zcloud",
        reason: "zcloud_project_not_found",
        answer: "Ik herken het zCloud-project in deze opdracht niet."
      };
    }

    if (selected.ambiguous) {
      return {
        enabled: false,
        provider: "zcloud",
        reason: "zcloud_project_ambiguous",
        answer: "Meerdere zCloud-projecten passen bij deze opdracht; ik heb niets gestart."
      };
    }

    const { project, alias } = selected;
    if (!isGenericContinuation(text, [alias, ...project.aliases])) {
      return {
        enabled: false,
        provider: "zcloud",
        reason: "zcloud_custom_task_not_supported",
        answer:
          "Ik heb deze specifieke opdracht nog niet verstuurd. " +
          "zCloud kan via Raise AI nu alleen veilig een bestaand project starten of verder laten gaan."
      };
    }

    const action = project.active ? "push" : "start";

    try {
      const { response, body, jsonMediaType } = await jsonFetch(
        fetchImpl,
        root + "/api/runner-control",
        {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: JSON.stringify({
            project_id: project.base_project_id,
            action
          })
        }
      );

      if (!response.ok) {
        return {
          enabled: false,
          provider: "zcloud",
          reason: "zcloud_command_rejected",
          answer: "zCloud heeft de opdracht niet geaccepteerd."
        };
      }

      if (
        !jsonMediaType ||
        body === null ||
        typeof body !== "object" ||
        Array.isArray(body) ||
        body.ok !== true ||
        !Number.isSafeInteger(body.command_id) ||
        body.command_id < 1 ||
        body.status !== "pending" ||
        body.active !== true ||
        body.desired_state !== "running" ||
        typeof body.deduplicated !== "boolean" ||
        body.forced !== false
      ) {
        return {
          enabled: false,
          provider: "zcloud",
          reason: "zcloud_invalid_ack",
          answer: "zCloud gaf geen geldige bevestiging; ik meld deze opdracht niet als gestart."
        };
      }

      return {
        enabled: true,
        provider: "zcloud",
        reason: "zcloud_command_queued",
        commandId: body.command_id,
        answer:
          project.name +
          (action === "start"
            ? " is gestart in zCloud."
            : " heeft een nieuwe push gekregen in zCloud.")
      };
    } catch {
      return {
        enabled: false,
        provider: "zcloud",
        reason: "zcloud_unavailable",
        answer: "zCloud is nu niet bereikbaar."
      };
    }
  };
}
