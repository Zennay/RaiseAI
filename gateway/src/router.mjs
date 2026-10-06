const PROJECTS = /\b(ftmo|haxlab|ulab|z\s*cloud|raise\s*ai|supa|flowly|z\s*ssh|light\s*up|z\s*guard)\b/i;
const EXECUTION = /\b(ga\s+door|werk\s+verder|start|fix|repareer|voer\s+uit|uitvoeren|deploy|build(?:en)?|bouw|commit|push|test(?:en)?|implementeer|update|maak|onderzoek\s+en)\b/i;
const PROJECT_QUESTION = /^\s*(wie|wat|waar|wanneer|waarom|hoe|hoeveel|welk|welke|is|zijn|staat|staan)\b/i;
const PROJECT_NEGATION = /\b(niet|geen|nooit|zonder)\b/i;
const EXPLANATION = /^\s*(?:(?:kun|kan)\s+je(?:\s+me)?\s+(?:uitleggen|vertellen)|leg(?:\s+me)?\s+uit|vertel(?:\s+me)?\s+(?:hoe|waarom|wat|meer\s+over|iets\s+over)|geef(?:\s+me)?\s+(?:uitleg|informatie|info)\s+over|beschrijf|licht(?:\s+me)?\s+toe|ik\s+(?:wil\s+(?:weten|uitleg|informatie)|vraag\s+me\s+af|ben\s+benieuwd))\b/i;
const HOME = /\b(google\s+home|home\s+assistant|lamp(?:en)?|licht(?:en)?|thermostaat|verwarming|speaker|tv|televisie|woonkamer|slaapkamer|keuken)\b/i;
const HOME_ACTION = /\b(aan|uit|zet|dim|verhoog|verlaag|speel|pauzeer|stop)\b/i;
const HOME_QUESTION = /^\s*(wie|wat|waar|wanneer|waarom|hoe|hoeveel|welk|welke|is|zijn|staat|staan)\b/i;
const HOME_STATE_STATEMENT = /\b(?:is|zijn|staat|staan|blijft|blijven)\b[^.!?]*\b(?:aan|uit)\b/i;
const HOME_QUERY_REQUEST = /^\s*(?:kun|kan)\s+je(?:\s+me)?\s+(?:zeggen|controleren|checken)\s+(?:of|wat|hoe|waarom|wanneer|waar)\b/i;
const HOME_NEGATION = /\b(niet|geen|nooit|zonder)\b/i;
const CURRENT = /\b(vandaag|nu|actueel|laatste|nieuwste|recent|weer|temperatuur|nieuws|verkeer|koers|prijs|stand|uitslag)\b/i;
const DEEP = /\b(analyseer|vergelijk|architectuur|debug|onderzoek|strategie|trade-?off|optimaliseer|ontwerp|implementeer|waarom|stappenplan|code|programmeer)\b/i;

export function classifyIntent(rawText) {
  const text = String(rawText ?? "").trim();
  if (!text) throw new TypeError("text is required");

  if (
    PROJECTS.test(text) &&
    EXECUTION.test(text) &&
    !PROJECT_QUESTION.test(text) &&
    !PROJECT_NEGATION.test(text) &&
    !EXPLANATION.test(text)
  ) {
    return {
      route: "zcloud_task",
      target: "zcloud.worker",
      connector: "zcloud",
      requiresConnector: true,
      reason: "project_execution"
    };
  }

  if (
    HOME.test(text) &&
    HOME_ACTION.test(text) &&
    !HOME_QUESTION.test(text) &&
    !HOME_STATE_STATEMENT.test(text) &&
    !HOME_QUERY_REQUEST.test(text) &&
    !HOME_NEGATION.test(text) &&
    !EXPLANATION.test(text)
  ) {
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
