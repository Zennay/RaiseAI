import test from "node:test";
import assert from "node:assert/strict";
import { classifyIntent } from "../src/router.mjs";

test("routes project execution to zCloud without an LLM classifier", () => {
  assert.equal(classifyIntent("Ga door met FTMO en test de volgende gate").route, "zcloud_task");
});

test("routes home device commands directly", () => {
  assert.equal(classifyIntent("Zet de lampen in de woonkamer uit").route, "smart_home");
});

test("routes freshness-sensitive questions to search", () => {
  assert.equal(classifyIntent("Wat is het laatste nieuws over OpenAI vandaag?").route, "current_info");
});

test("routes normal informational questions to the cheap AI lane", () => {
  assert.equal(classifyIntent("Leg kubernetes pods simpel uit").route, "quick_ai");
});
