import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { spawnSync } from "node:child_process";

import { readKeyValueFile } from "../deploy/read-key-value-file.mjs";

function withTempDir(fn) {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "raise-state-file-"));
  try {
    return fn(root);
  } finally {
    fs.rmSync(root, { recursive: true, force: true });
  }
}

test("deployment state parser returns canonical key-value data", () => {
  withTempDir(root => {
    const file = path.join(root, "gateway.env");
    fs.writeFileSync(
      file,
      "# comment\nRAISE_PORT=8787\nRAISE_DEPLOY_REVISION=abc123\n",
      "utf8"
    );

    assert.deepEqual(
      [...readKeyValueFile(file)],
      [
        ["RAISE_PORT", "8787"],
        ["RAISE_DEPLOY_REVISION", "abc123"]
      ]
    );
  });
});

test("deployment state parser rejects duplicate keys", () => {
  withTempDir(root => {
    const file = path.join(root, "gateway.env");
    fs.writeFileSync(
      file,
      "RAISE_DEPLOY_REVISION=first\nRAISE_DEPLOY_REVISION=second\n",
      "utf8"
    );

    assert.throws(
      () => readKeyValueFile(file),
      /duplicate deployment state key RAISE_DEPLOY_REVISION/
    );
  });
});

test("deployment state parser rejects symlink inputs", () => {
  withTempDir(root => {
    const target = path.join(root, "target.env");
    const link = path.join(root, "gateway.env");
    fs.writeFileSync(target, "RAISE_PORT=8787\n", "utf8");
    fs.symlinkSync(target, link);

    assert.throws(
      () => readKeyValueFile(link),
      /regular non-symlink file/
    );
  });
});

test("deployment state parser rejects FIFO inputs without blocking", () => {
  withTempDir(root => {
    const fifo = path.join(root, "gateway.env");
    const result = spawnSync("mkfifo", [fifo], { encoding: "utf8" });
    assert.equal(result.status, 0, result.stderr);

    const started = Date.now();
    assert.throws(() => readKeyValueFile(fifo), /regular file/);
    assert.ok(Date.now() - started < 1000, "FIFO rejection must not wait for a writer");
  });
});

test("deployment state parser enforces a bounded read", () => {
  withTempDir(root => {
    const file = path.join(root, "gateway.env");
    fs.writeFileSync(file, "A=" + "x".repeat(40) + "\n", "utf8");

    assert.throws(
      () => readKeyValueFile(file, { maxBytes: 16 }),
      /exceeds 16 bytes/
    );
  });
});

test("deployment state parser rejects malformed UTF-8", () => {
  withTempDir(root => {
    const file = path.join(root, "gateway.env");
    fs.writeFileSync(file, Buffer.from([0x41, 0x3d, 0xc3, 0x28, 0x0a]));

    assert.throws(
      () => readKeyValueFile(file),
      /not valid UTF-8/
    );
  });
});

test("deployment state parser rejects NUL bytes", () => {
  withTempDir(root => {
    const file = path.join(root, "gateway.env");
    fs.writeFileSync(file, Buffer.from("RAISE_PORT=8787\0shadow\n", "utf8"));

    assert.throws(
      () => readKeyValueFile(file),
      /contains NUL bytes/
    );
  });
});

test("missing state is only tolerated when explicitly requested", () => {
  withTempDir(root => {
    const missing = path.join(root, "missing.env");

    assert.deepEqual(
      [...readKeyValueFile(missing, { allowMissing: true })],
      []
    );
    assert.throws(
      () => readKeyValueFile(missing),
      /regular non-symlink file/
    );
  });
});
