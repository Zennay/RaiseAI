import test from "node:test";
import assert from "node:assert/strict";
import { createConversationMemory } from "../src/conversation-memory.mjs";

test("conversation memory continues within the inactivity window", () => {
  let clock = 1_000;
  const memory = createConversationMemory({
    now: () => clock,
    ttlMs: 10 * 60 * 1000
  });

  assert.equal(memory.record("galaxy-watch-7", "Wie is Ada?", "Ada Lovelace."), true);
  clock += 9 * 60 * 1000;

  assert.deepEqual(memory.get("galaxy-watch-7"), [
    { user: "Wie is Ada?", assistant: "Ada Lovelace." }
  ]);
});

test("conversation memory starts fresh after ten minutes of inactivity", () => {
  let clock = 1_000;
  const memory = createConversationMemory({
    now: () => clock,
    ttlMs: 10 * 60 * 1000
  });

  memory.record("galaxy-watch-7", "eerste", "antwoord");
  clock += 10 * 60 * 1000;

  assert.deepEqual(memory.get("galaxy-watch-7"), []);
});

test("conversation memory is bounded to the newest three turns", () => {
  const memory = createConversationMemory({ maxTurns: 3 });
  for (let i = 1; i <= 5; i += 1) {
    memory.record("galaxy-watch-7", "vraag-" + i, "antwoord-" + i);
  }

  assert.deepEqual(
    memory.get("galaxy-watch-7").map((turn) => turn.user),
    ["vraag-3", "vraag-4", "vraag-5"]
  );
});

test("invalid session keys are ignored", () => {
  const memory = createConversationMemory();
  assert.equal(memory.record("watch id with spaces", "vraag", "antwoord"), false);
  assert.deepEqual(memory.get("watch id with spaces"), []);
});
