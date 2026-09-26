const PROJECTS = /\b(ftmo|haxlab|ulab|zcloud|raise\s*ai|supa|flowly)\b/i;
const EXECUTION = /\b(ga\s+door|werk\s+verder|fix|repareer|voer\s+uit|uitvoeren|deploy|build|bouw|commit|push|test|implementeer|update|maak|onderzoek\s+en)\b/i;
const HOME = /\b(google\s+home|home\s+assistant|lamp(?:en)?|licht(?:en)?|thermostaat|verwarming|speaker|tv|televisie|woonkamer|slaapkamer|keuken)\b/i;
const HOME_ACTION = /\b(aan|uit|zet|dim|verhoog|verlaag|speel|pauzeer|stop|volume|temperatuur)\b/i;
const CURRENT = /\b(vandaag|nu|actueel|laatste|nieuwste|recent|weer|temperatuur|nieuws|verkeer|koers|prijs|stand|uitslag)\b/i;

export function classifyIntent(rawText) {
  const text = String(rawText ?? "").trim();
  if (!text) throw new TypeError("text is required");

  if (PROJECTS.test(text) && EXECUTION.test(text)) {
    return {
      route: "zcloud_task",
      target: "zcloud.worker",
      connector: "zcloud",
      requiresConnector: true,
      reason: "project_execution"
    };
  }

  if (HOME.test(text) && HOME_ACTION.test(text)) {
    return {
      route: "smart_home",
      target: "home.command",
      connector: "google_home",
      requiresConnector: true,
      reason: "home_command"
    };
  }

  if (CURRENT.test(text)) {
    return {
      route: "current_info",
      target: "ai.search",
      connector: "web_search",
      requiresConnector: true,
      reason: "freshness_required"
    };
  }

  return {
    route: "quick_ai",
    target: "ai.fast",
    connector: "llm",
    requiresConnector: true,
    reason: "default"
  };
}
