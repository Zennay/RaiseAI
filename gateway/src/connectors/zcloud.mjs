const DEFAULT_BASE_URL = "http://127.0.0.1:8765";

function normalize(value) {
  return String(value ?? "")
    .normalize("NFKD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, " ")
    .trim()
    .replace(/\s+/g, " ");
}

function aliasesFor(project) {
  const aliases = new Set();
  const base = normalize(project.base_project_id);
  const name = normalize(String(project.name ?? "").split("·")[0]);

  if (base) aliases.add(base);
  if (name) aliases.add(name);

  if (base === "raiseai") aliases.add("raise ai");
  if (base === "ulab") aliases.add("u lab");

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

  for (const target of Object.values(payload.projects)) {
    if (target === null || typeof target !== "object" || Array.isArray(target)) {
      throw new Error("zcloud_targets_invalid");
    }
    if (typeof target.base_project_id !== "string" || !target.base_project_id.trim()) {
      throw new Error("zcloud_targets_invalid");
    }
    if (typeof target.active !== "boolean") {
      throw new Error("zcloud_targets_invalid");
    }
    if (target.name !== undefined && target.name !== null && typeof target.name !== "string") {
      throw new Error("zcloud_targets_invalid");
    }

    const base = target.base_project_id.trim();
    const current = groups.get(base) ?? {
      base_project_id: base,
      name: String(target.name ?? base).split("·")[0].trim() || base,
      active: false,
      aliases: new Set()
    };

    current.active ||= target.active;
    for (const alias of aliasesFor(target)) current.aliases.add(alias);
    groups.set(base, current);
  }

  return [...groups.values()].map(group => ({
    ...group,
    aliases: [...group.aliases].sort((a, b) => b.length - a.length)
  }));
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

async function jsonFetch(fetchImpl, url, options = {}) {
  const response = await fetchImpl(url, {
    ...options,
    signal: options.signal ?? AbortSignal.timeout(2_500)
  });

  const body = await response.json().catch(() => null);
  return { response, body };
}

export function createZCloudExecutor({
  baseUrl = DEFAULT_BASE_URL,
  fetchImpl = globalThis.fetch
} = {}) {
  const root = baseUrl.replace(/\/$/, "");

  return async function execute(decision, text) {
    if (decision.route !== "zcloud_task") return null;

    let targets;
    try {
      const { response, body } = await jsonFetch(
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
      const { response, body } = await jsonFetch(
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
        const errorMessage =
          typeof body?.error === "string" && body.error.trim()
            ? body.error.trim()
            : "zCloud heeft de opdracht niet geaccepteerd.";
        return {
          enabled: false,
          provider: "zcloud",
          reason: "zcloud_command_rejected",
          answer: errorMessage
        };
      }

      if (
        body === null ||
        typeof body !== "object" ||
        Array.isArray(body) ||
        body.ok !== true ||
        !Number.isSafeInteger(body.command_id) ||
        body.command_id < 1 ||
        body.status !== "pending"
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
