import test from "node:test";
import assert from "node:assert/strict";
import { classifyIntent } from "../src/router.mjs";

test("routes project execution to zCloud without an LLM classifier", () => {
  assert.equal(classifyIntent("Ga door met FTMO en test de volgende gate").route, "zcloud_task");
});

test("project questions never dispatch work from execution-like words", () => {
  for (const text of [
    "Hoe test ik HaxLab lokaal?",
    "Wat test zCloud voordat een worker start?",
    "Waarom build Supa niet automatisch?",
    "Welke commit update Raise AI?",
    "Waar maak ik een nieuwe uLab release?"
  ]) {
    assert.notEqual(classifyIntent(text).route, "zcloud_task", text);
  }

  assert.equal(classifyIntent("Test HaxLab en commit de fix").route, "zcloud_task");
  assert.equal(classifyIntent("Werk verder aan zCloud").route, "zcloud_task");
  assert.equal(classifyIntent("Kan je Supa builden en testen?").route, "zcloud_task");
});

test("project explanation prompts stay informational even with execution vocabulary", () => {
  for (const text of [
    "Kun je uitleggen hoe ik HaxLab test?",
    "Kan je me vertellen waarom zCloud deze build test?",
    "Leg me uit hoe ik Supa build",
    "Vertel me hoe ik Raise AI test"
  ]) {
    assert.notEqual(classifyIntent(text).route, "zcloud_task", text);
  }

  assert.equal(classifyIntent("Kan je Raise AI testen?").route, "zcloud_task");
});

test("broader project explanation prompts never dispatch work", () => {
  for (const text of [
    "Vertel me meer over het testen van HaxLab",
    "Vertel iets over waarom zCloud deze build test",
    "Geef me uitleg over het pushen van Supa",
    "Beschrijf hoe ik Raise AI test",
    "Licht toe waarom uLab een update nodig heeft"
  ]) {
    assert.notEqual(classifyIntent(text).route, "zcloud_task", text);
  }
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

test("home explanation prompts never actuate devices", () => {
  for (const text of [
    "Vertel me meer over de lampen uit zetten",
    "Vertel iets over waarom de verwarming aan staat",
    "Geef me uitleg over de thermostaat uit zetten",
    "Beschrijf hoe ik de speaker stop",
    "Licht toe waarom de tv uit staat"
  ]) {
    assert.notEqual(classifyIntent(text).route, "smart_home", text);
  }
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
