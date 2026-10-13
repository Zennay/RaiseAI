import fs from "node:fs";


const DEFAULT_MAX_BYTES = 1024 * 1024;


function requiredOpenFlag(name) {
  const value = fs.constants[name];
  if (!Number.isInteger(value)) {
    throw new Error(`bounded regular-file reads require ${name} support`);
  }
  return value;
}


export function readBoundedRegularFile(
  file,
  { maxBytes = DEFAULT_MAX_BYTES } = {},
) {
  if (!Number.isInteger(maxBytes) || maxBytes <= 0) {
    throw new Error("regular-file maxBytes must be a positive integer");
  }

  const flags =
    fs.constants.O_RDONLY |
    requiredOpenFlag("O_NOFOLLOW") |
    requiredOpenFlag("O_NONBLOCK");

  let fd;
  try {
    fd = fs.openSync(file, flags);
  } catch (error) {
    throw new Error(`input must be a regular non-symlink file: ${file}`, {
      cause: error,
    });
  }

  try {
    const stat = fs.fstatSync(fd);
    if (!stat.isFile()) {
      throw new Error(`input must be a regular file: ${file}`);
    }
    if (stat.size > maxBytes) {
      throw new Error(`input exceeds ${maxBytes} bytes: ${file}`);
    }

    const chunks = [];
    let total = 0;
    while (total <= maxBytes) {
      const remaining = maxBytes + 1 - total;
      const chunk = Buffer.allocUnsafe(Math.min(16 * 1024, remaining));
      const bytesRead = fs.readSync(fd, chunk, 0, chunk.length, null);
      if (bytesRead === 0) break;
      total += bytesRead;
      chunks.push(chunk.subarray(0, bytesRead));
    }

    if (total > maxBytes) {
      throw new Error(`input exceeds ${maxBytes} bytes: ${file}`);
    }

    return Buffer.concat(chunks, total);
  } finally {
    fs.closeSync(fd);
  }
}
