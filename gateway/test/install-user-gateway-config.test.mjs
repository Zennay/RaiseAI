import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { spawnSync } from "node:child_process";

const testDir = path.dirname(fileURLToPath(import.meta.url));
const installer = path.resolve(testDir, "../deploy/install-user-gateway.sh");

function runInvalidConfig(overrides) {
  const home = fs.mkdtempSync(path.join(os.tmpdir(), "raise-installer-config-"));
  try {
    const result = spawnSync("bash", [installer], {
      encoding: "utf8",
      env: {
        ...process.env,
        HOME: home,
        RAISE_DEPLOY_REVISION: "a".repeat(40),
        RAISE_PUBLIC_HOST: "raise.example",
        RAISE_PUBLIC_PORT: "8787",
        ...overrides
      }
    });
    return {
      status: result.status,
      stderr: result.stderr,
      configCreated: fs.existsSync(path.join(home, ".config", "raiseai"))
    };
  } finally {
    fs.rmSync(home, { recursive: true, force: true });
  }
}

test("installer rejects malformed public hosts before side effects", () => {
  for (const host of [
    " raise.example",
    "raise.example ",
    "raise..example",
    ".raise.example",
    "raise.example.",
    "-raise.example",
    "raise-.example",
    "raise/example",
    "raise:443",
    "raise\nexample",
    "raise\texample",
    "raise\rexample",
    "a".repeat(64) + ".example",
    "a".repeat(254)
  ]) {
    const result = runInvalidConfig({ RAISE_PUBLIC_HOST: host });
    assert.notEqual(result.status, 0, JSON.stringify(host));
    assert.match(result.stderr, /Invalid RAISE_PUBLIC_HOST/, JSON.stringify(host));
    assert.equal(result.configCreated, false, JSON.stringify(host));
  }
});

test("installer rejects malformed public ports before side effects", () => {
  for (const port of [
    "0",
    "00080",
    "65536",
    " 8787",
    "8787 ",
    "+8787",
    "-1",
    "1e3",
    "8787.0",
    "443\n8443"
  ]) {
    const result = runInvalidConfig({ RAISE_PUBLIC_PORT: port });
    assert.notEqual(result.status, 0, JSON.stringify(port));
    assert.match(result.stderr, /Invalid RAISE_PUBLIC_PORT/, JSON.stringify(port));
    assert.equal(result.configCreated, false, JSON.stringify(port));
  }
});
