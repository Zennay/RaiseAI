import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";


const HERE = path.dirname(fileURLToPath(import.meta.url));
const PACKAGE_PATH = path.resolve(HERE, "..", "package.json");
const packageJson = JSON.parse(fs.readFileSync(PACKAGE_PATH, "utf8"));

const DEPENDENCY_SECTIONS = [
  "dependencies",
  "devDependencies",
  "optionalDependencies",
  "peerDependencies",
];
const INSTALL_LIFECYCLE_SCRIPTS = [
  "preinstall",
  "install",
  "postinstall",
  "prepare",
  "prepack",
  "postpack",
];


test("gateway package remains private ESM with explicit runtime scripts", () => {
  assert.equal(packageJson.name, "raise-ai-gateway");
  assert.equal(packageJson.private, true);
  assert.equal(packageJson.type, "module");
  assert.deepEqual(packageJson.scripts, {
    start: "node src/server.mjs",
    test: "node --test",
  });
  assert.deepEqual(packageJson.engines, { node: ">=22" });
});


test("gateway package keeps a zero third-party dependency surface", () => {
  for (const section of DEPENDENCY_SECTIONS) {
    assert.deepEqual(
      packageJson[section] ?? {},
      {},
      `${section} must remain empty unless the supply-chain contract is intentionally reviewed`,
    );
  }
});


test("gateway package exposes no install-time lifecycle hooks", () => {
  const scripts = packageJson.scripts ?? {};
  for (const script of INSTALL_LIFECYCLE_SCRIPTS) {
    assert.equal(
      Object.hasOwn(scripts, script),
      false,
      `${script} must not execute during package installation`,
    );
  }
});
