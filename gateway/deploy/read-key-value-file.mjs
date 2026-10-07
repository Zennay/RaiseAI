import fs from "node:fs";
import { TextDecoder } from "node:util";

const DEFAULT_MAX_BYTES = 64 * 1024;

function requiredOpenFlag(name) {
  const value = fs.constants[name];
  if (!Number.isInteger(value)) {
    throw new Error(`deployment state parsing requires ${name} support`);
  }
  return value;
}

function readBoundedUtf8(fd, maxBytes, file) {
  const chunks = [];
  let total = 0;

  while (total <= maxBytes) {
    const remaining = maxBytes + 1 - total;
    const chunk = Buffer.allocUnsafe(Math.min(4096, remaining));
    const bytesRead = fs.readSync(fd, chunk, 0, chunk.length, null);
    if (bytesRead === 0) break;
    total += bytesRead;
    chunks.push(chunk.subarray(0, bytesRead));
  }

  if (total > maxBytes) {
    throw new Error(`deployment state file exceeds ${maxBytes} bytes: ${file}`);
  }

  try {
    return new TextDecoder("utf-8", { fatal: true }).decode(Buffer.concat(chunks));
  } catch (error) {
    throw new Error(`deployment state file is not valid UTF-8: ${file}`, {
      cause: error
    });
  }
}

export function readKeyValueFile(
  file,
  { allowMissing = false, maxBytes = DEFAULT_MAX_BYTES } = {}
) {
  if (!Number.isInteger(maxBytes) || maxBytes <= 0) {
    throw new Error("deployment state maxBytes must be a positive integer");
  }

  const flags =
    fs.constants.O_RDONLY |
    requiredOpenFlag("O_NOFOLLOW") |
    requiredOpenFlag("O_NONBLOCK");

  let fd;
  try {
    fd = fs.openSync(file, flags);
  } catch (error) {
    if (allowMissing && error?.code === "ENOENT") {
      return new Map();
    }
    throw new Error(`deployment state must be a regular non-symlink file: ${file}`, {
      cause: error
    });
  }

  try {
    const stat = fs.fstatSync(fd);
    if (!stat.isFile()) {
      throw new Error(`deployment state must be a regular file: ${file}`);
    }
    if (stat.size > maxBytes) {
      throw new Error(
        `deployment state file exceeds ${maxBytes} bytes: ${file}`
      );
    }

    const text = readBoundedUtf8(fd, maxBytes, file);
    const values = new Map();

    for (const rawLine of text.split("\n")) {
      const line = rawLine.trim();
      if (!line || line.startsWith("#")) continue;

      const separator = rawLine.indexOf("=");
      if (separator <= 0) {
        throw new Error(`malformed deployment state line in ${file}`);
      }

      const key = rawLine.slice(0, separator).trim();
      const value = rawLine.slice(separator + 1).trim();
      if (!key) {
        throw new Error(`empty deployment state key in ${file}`);
      }
      if (values.has(key)) {
        throw new Error(`duplicate deployment state key ${key} in ${file}`);
      }
      values.set(key, value);
    }

    return values;
  } finally {
    fs.closeSync(fd);
  }
}
