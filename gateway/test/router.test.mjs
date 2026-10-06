import test from "node:test";
import assert from "node:assert/strict";
import { classifyIntent } from "../src/router.mjs";

test("routes project execution to zCloud without an LLM classifier", () => {
  assert.equal(classifyIntent("Ga door met FTMO en test de volgende gate").route, "zcloud_task");
});

test("routes current zCloud portfolio project continuations", () => {
  for (const text of [
    "Werk verder aan LightUp",
    "Ga door met zSSH",
    "Werk verder aan zGuard"
  ]) {
    assert.equal(classifyIntent(text).route, "zcloud_task", text);
  }
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
    "Geef me uitleg over wanneer ik Supa push",
    "Beschrijf hoe ik Raise AI test",
    "Licht toe waarom uLab een update nodig heeft"
  ]) {
    assert.notEqual(classifyIntent(text).route, "zcloud_task", text);
  }
});

test("first-person informational project prompts never dispatch work", () => {
  for (const text of [
    "Ik wil weten hoe ik HaxLab test",
    "Ik vraag me af waarom zCloud deze build test",
    "Ik ben benieuwd wanneer ik Supa push",
    "Ik wil uitleg over waarom Raise AI een update nodig heeft",
    "Vertel me wat er gebeurt als ik uLab test"
  ]) {
    assert.notEqual(classifyIntent(text).route, "zcloud_task", text);
  }

  assert.equal(classifyIntent("Ik wil HaxLab testen").route, "zcloud_task");
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

test("home state statements never actuate devices", () => {
  for (const text of [
    "De verwarming staat aan",
    "De lampen in de woonkamer staan uit",
    "Mijn tv is uit",
    "De speaker is aan"
  ]) {
    assert.notEqual(classifyIntent(text).route, "smart_home", text);
  }

  assert.equal(classifyIntent("de lampen uit").route, "smart_home");
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

test("first-person informational home prompts never actuate devices", () => {
  for (const text of [
    "Ik wil weten hoe ik de thermostaat uit zet",
    "Ik vraag me af waarom de verwarming aan staat",
    "Ik ben benieuwd hoe ik de speaker stop",
    "Ik wil informatie over wanneer de lampen uit staan",
    "Vertel me wat er gebeurt als ik de tv uit zet"
  ]) {
    assert.notEqual(classifyIntent(text).route, "smart_home", text);
  }

  assert.equal(classifyIntent("Ik wil de verwarming aan").route, "smart_home");
});

test("negated home prompts never actuate devices", () => {
  for (const text of [
    "Zet de lamp niet uit",
    "Zet de verwarming niet aan",
    "Stop de speaker niet",
    "Doe de tv niet uit",
    "Zet geen lampen uit",
    "Zet geen verwarming aan",
    "Zet de lampen nooit aan",
    "Stop de speaker nooit",
    "Doe dit zonder de lamp uit te zetten",
    "Ga door zonder de verwarming aan te zetten"
  ]) {
    assert.notEqual(classifyIntent(text).route, "smart_home", text);
  }

  assert.equal(classifyIntent("Zet de lamp uit").route, "smart_home");
  assert.equal(classifyIntent("Stop de speaker").route, "smart_home");
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
