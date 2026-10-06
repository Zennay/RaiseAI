import test from "node:test";
import assert from "node:assert/strict";
import { classifyIntent } from "../src/router.mjs";

test("routes project execution to zCloud without an LLM classifier", () => {
  assert.equal(classifyIntent("Ga door met FTMO en test de volgende gate").route, "zcloud_task");
});

test("routes home device commands directly", () => {
  assert.equal(classifyIntent("Zet de lampen in de woonkamer uit").route, "smart_home");
  assert.equal(classifyIntent("Zet de thermostaat op 20 graden").route, "smart_home");
  assert.equal(classifyIntent("Verhoog het volume van de speaker").route, "smart_home");
});

test("home-related status questions never become device commands from nouns alone", () => {
  assert.equal(
    classifyIntent("Wat is de temperatuur in de woonkamer?").route,
    "current_info"
  );
  assert.equal(
    classifyIntent("Wat is het volume van de speaker?").route,
    "quick_ai"
  );
});

test("home questions never dispatch commands from action-like words", () => {
  for (const text of [
    "Is de verwarming aan?",
    "Zijn de lampen uit?",
    "Staat de thermostaat aan?",
    "Staan de lichten uit?",
    "Waarom staat de verwarming aan?",
    "Hoe zet ik de thermostaat uit?",
    "Wanneer gaat de tv uit?",
    "Welke lamp staat aan?",
    "Waar stop ik de speaker?"
  ]) {
    assert.notEqual(classifyIntent(text).route, "smart_home", text);
  }

  assert.equal(classifyIntent("verwarming aan").route, "smart_home");
  assert.equal(classifyIntent("lampen uit").route, "smart_home");
  assert.equal(classifyIntent("zet de thermostaat uit").route, "smart_home");
});

test("routes freshness-sensitive questions to search", () => {
  assert.equal(classifyIntent("Wat is het laatste nieuws over OpenAI vandaag?").route, "current_info");
});

test("routes complex questions to the stronger AI lane", () => {
  assert.equal(
    classifyIntent("Analyseer deze architectuur en vergelijk de trade-offs").route,
    "deep_ai"
  );
});

test("routes normal informational questions to the cheap AI lane", () => {
  assert.equal(classifyIntent("Leg kubernetes pods simpel uit").route, "quick_ai");
});