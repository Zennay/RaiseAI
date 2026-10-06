const PROJECTS = /\b(ftmo|haxlab|ulab|zcloud|raise\s*ai|supa|flowly)\b/i;
const EXECUTION = /\b(ga\s+door|werk\s+verder|fix|repareer|voer\s+uit|uitvoeren|deploy|build|bouw|commit|push|test|implementeer|update|maak|onderzoek\s+en)\b/i;
const HOME = /\b(google\s+home|home\s+assistant|lamp(?:en)?|licht(?:en)?|thermostaat|verwarming|speaker|tv|televisie|woonkamer|slaapkamer|keuken)\b/i;
const HOME_ACTION = /\b(aan|uit|zet|dim|verhoog|verlaag|speel|pauzeer|stop)\b/i;\nconst HOME_STATUS_QUESTION = /^\\s*(is|zijn|staat|staan)\\b/i;
const CURRENT = /\b(vandaag|nu|actueel|laatste|nieuwste|recent|weer|temperatuur|nieuws|verkeer|koers|prijs|stand|uitslag)\b/i;
const DEEP = /\b(analyseer|vergelijk|architectuur|debug|onderzoek|strategie|trade-?off|optimaliseer|ontwerp|implementeer|waarom|stappenplan|code|programmeer)\b/i;

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

  if (HOME.test(text) && HOME_ACTION.test(text) && !HOME_STATUS_QUESTION.test(text)) {
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

  if (DEEP.test(text) || text.length > 220) {
    return {
      route: "deep_ai",
      target: "ai.reasoning",
      connector: "llm",
      requiresConnector: true,
      reason: DEEP.test(text) ? "complex_request" : "long_request"
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