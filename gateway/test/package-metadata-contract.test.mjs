import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";


const PACKAGE_URL = new URL("../package.json", import.meta.url);
const metadata = JSON.parse(await readFile(PACKAGE_URL, "utf8"));

const DEPENDENCY_SECTIONS = [
  "dependencies",
  "devDependencies",
  "optionalDependencies",
  "peerDependencies",
  "bundledDependencies",
];

const AUTOMATIC_LIFECYCLE_SCRIPTS = [
  "preinstall",
  "install",
  "postinstall",
  "prepublish",
  "prepublishOnly",
  "prepare",
];


test("gateway package metadata stays private and runtime-pinned", () => {
  assert.equal(metadata.name, "raise-ai-gateway");
  assert.equal(metadata.private, true);
  assert.equal(metadata.type, "module");
  assert.equal(metadata.engines?.node, ">=22");
  assert.equal(metadata.scripts?.start, "node src/server.mjs");
  assert.equal(metadata.scripts?.test, "node --test");
});


test("gateway stays zero-dependency unless supply-chain scope is reviewed", () => {
  for (const section of DEPENDENCY_SECTIONS) {
    assert.equal(
      Object.hasOwn(metadata, section),
      false,
      `${section} must remain absent until an explicit dependency review adds it`,
    );
  }
});


test("gateway package cannot gain automatic npm lifecycle execution", () => {
  const scripts = metadata.scripts ?? {};

  for (const script of AUTOMATIC_LIFECYCLE_SCRIPTS) {
    assert.equal(
      Object.hasOwn(scripts, script),
      false,
      `${script} may execute during install/publish and requires explicit review`,
    );
  }
});
