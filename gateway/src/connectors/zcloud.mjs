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
  const groups = new Map();

  for (const target of Object.values(payload?.projects ?? {})) {
    const base = String(target.base_project_id ?? "").trim();
    if (!base) continue;

    const current = groups.get(base) ?? {
      base_project_id: base,
      name: String(target.name ?? base).split("·")[0].trim() || base,
      active: false,
      aliases: new Set()
    };

    current.active ||= Boolean(target.active);
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
  return candidates[0] ?? null;
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

  const body = await response.json().catch(() => ({}));
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
    } catch {
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
        return {
          enabled: false,
          provider: "zcloud",
          reason: "zcloud_command_rejected",
          answer:
            typeof body.error === "string"
              ? body.error
              : "zCloud heeft de opdracht niet geaccepteerd."
        };
      }

      return {
        enabled: true,
        provider: "zcloud",
        reason: "zcloud_command_queued",
        commandId: body.command_id ?? null,
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
