import assert from "node:assert/strict";
import { execFileSync, spawnSync } from "node:child_process";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import test from "node:test";

import { readBoundedRegularFile } from "../deploy/read-regular-file.mjs";


function withTemporaryDirectory(fn) {
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), "raise-regular-file-"));
  try {
    return fn(directory);
  } finally {
    fs.rmSync(directory, { recursive: true, force: true });
  }
}


test("bounded regular-file reader preserves exact bytes", () => {
  withTemporaryDirectory(directory => {
    const file = path.join(directory, "certificate.pem");
    const payload = Buffer.from([0x00, 0x01, 0x7f, 0x80, 0xff]);
    fs.writeFileSync(file, payload);

    assert.deepEqual(readBoundedRegularFile(file), payload);
  });
});


test("bounded regular-file reader rejects symlink and directory inputs", () => {
  withTemporaryDirectory(directory => {
    const target = path.join(directory, "target.pem");
    const symlink = path.join(directory, "link.pem");
    fs.writeFileSync(target, "certificate");
    fs.symlinkSync(target, symlink);

    assert.throws(
      () => readBoundedRegularFile(symlink),
      /regular non-symlink file/,
    );
    assert.throws(
      () => readBoundedRegularFile(directory),
      /regular file/,
    );
  });
});


test("bounded regular-file reader rejects oversized input", () => {
  withTemporaryDirectory(directory => {
    const file = path.join(directory, "large.pem");
    fs.writeFileSync(file, Buffer.alloc(17, 0x41));

    assert.throws(
      () => readBoundedRegularFile(file, { maxBytes: 16 }),
      /exceeds 16 bytes/,
    );
  });
});


test("bounded regular-file reader rejects FIFO without blocking", () => {
  withTemporaryDirectory(directory => {
    const fifo = path.join(directory, "certificate.fifo");
    execFileSync("mkfifo", [fifo]);

    const helperUrl = new URL("../deploy/read-regular-file.mjs", import.meta.url).href;
    const script = `
      import { readBoundedRegularFile } from ${JSON.stringify(helperUrl)};
      try {
        readBoundedRegularFile(process.argv[1]);
        process.exit(2);
      } catch (error) {
        if (!/regular file/.test(String(error?.message ?? error))) {
          console.error(error);
          process.exit(3);
        }
      }
    `;

    const result = spawnSync(
      process.execPath,
      ["--input-type=module", "--eval", script, fifo],
      {
        encoding: "utf8",
        timeout: 1500,
      },
    );

    assert.equal(result.error, undefined, result.error?.message);
    assert.equal(result.status, 0, result.stderr);
  });
});
