const DEFAULT_TTL_MS = 10 * 60 * 1000;
const DEFAULT_MAX_TURNS = 3;
const MAX_PART_CHARS = 1200;

function normalizeSessionKey(value) {
  const key = String(value ?? "").trim();
  return /^[A-Za-z0-9._:-]{1,64}$/.test(key) ? key : null;
}

function normalizePart(value) {
  return String(value ?? "").trim().slice(0, MAX_PART_CHARS);
}

export function createConversationMemory({
  now = () => Date.now(),
  ttlMs = DEFAULT_TTL_MS,
  maxTurns = DEFAULT_MAX_TURNS
} = {}) {
  const sessions = new Map();
  const boundedTtlMs = Math.max(1_000, Number(ttlMs) || DEFAULT_TTL_MS);
  const boundedMaxTurns = Math.max(1, Math.min(Number(maxTurns) || DEFAULT_MAX_TURNS, 6));

  function get(sessionKey) {
    const key = normalizeSessionKey(sessionKey);
    if (!key) return [];

    const entry = sessions.get(key);
    if (!entry) return [];

    if (now() - entry.updatedAt >= boundedTtlMs) {
      sessions.delete(key);
      return [];
    }

    return entry.turns.map((turn) => ({ ...turn }));
  }

  function record(sessionKey, user, assistant) {
    const key = normalizeSessionKey(sessionKey);
    const userText = normalizePart(user);
    const assistantText = normalizePart(assistant);
    if (!key || !userText || !assistantText) return false;

    const turns = [
      ...get(key),
      { user: userText, assistant: assistantText }
    ].slice(-boundedMaxTurns);

    sessions.set(key, {
      updatedAt: now(),
      turns
    });
    return true;
  }

  return {
    get,
    record
  };
}
