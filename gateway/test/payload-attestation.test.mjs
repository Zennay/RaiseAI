import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import test from "node:test";
import { attestPayload, payloadManifest } from "../deploy/attest-payload.mjs";

function makePayload(root, { server = "export default 1;\n", extra = false } = {}) {
  fs.mkdirSync(path.join(root, "src"), { recursive: true });
  fs.writeFileSync(path.join(root, "package.json"), "{\"name\":\"raise\"}\n");
  fs.writeFileSync(path.join(root, "src", "server.mjs"), server);
  fs.writeFileSync(path.join(root, "src", "router.mjs"), "export const route = true;\n");
  if (extra) fs.writeFileSync(path.join(root, "src", "extra.mjs"), "extra\n");
}

test("payload manifest is deterministic for identical deploy payloads", () => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "raise-payload-"));
  const source = path.join(root, "source");
  const installed = path.join(root, "installed");
  makePayload(source);
  makePayload(installed);

  const result = attestPayload({ sourceRoot: source, installedRoot: installed });
  assert.equal(result.ok, true);
  assert.equal(result.reason, "payload_match");
  assert.equal(result.source_digest, result.installed_digest);
  assert.equal(result.source_file_count, 3);
  assert.equal(result.installed_file_count, 3);
});

test("payload attestation rejects changed installed bytes", () => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "raise-payload-"));
  const source = path.join(root, "source");
  const installed = path.join(root, "installed");
  makePayload(source);
  makePayload(installed, { server: "export default 2;\n" });

  const result = attestPayload({ sourceRoot: source, installedRoot: installed });
  assert.equal(result.ok, false);
  assert.equal(result.reason, "payload_mismatch");
  assert.notEqual(result.source_digest, result.installed_digest);
});

test("payload attestation rejects an unexpected installed file", () => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "raise-payload-"));
  const source = path.join(root, "source");
  const installed = path.join(root, "installed");
  makePayload(source);
  makePayload(installed, { extra: true });

  const result = attestPayload({ sourceRoot: source, installedRoot: installed });
  assert.equal(result.ok, false);
  assert.equal(result.installed_file_count, result.source_file_count + 1);
});

test("payload manifest hashes only deploy files and never serializes their contents", () => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "raise-payload-"));
  makePayload(root, { server: "OPENROUTER_API_KEY=should-never-appear\n" });

  const manifest = payloadManifest(root);
  const serialized = JSON.stringify(manifest);
  assert.match(manifest.digest, /^[a-f0-9]{64}$/);
  assert.equal(serialized.includes("should-never-appear"), false);
  assert.deepEqual(Object.keys(manifest).sort(), ["digest", "file_count"]);
});
