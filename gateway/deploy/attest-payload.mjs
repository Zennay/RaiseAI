#!/usr/bin/env node
import crypto from "node:crypto";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const deployDir = path.dirname(fileURLToPath(import.meta.url));
const defaultSourceRoot = path.resolve(deployDir, "..");
const defaultInstalledRoot = path.join(os.homedir(), ".local", "share", "raise-gateway");

function regularFiles(root, relativeDir) {
  const dir = path.join(root, relativeDir);
  if (!fs.existsSync(dir)) return [];
  const out = [];

  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const relative = path.posix.join(relativeDir, entry.name);
    const absolute = path.join(root, relative);
    const stat = fs.lstatSync(absolute);

    if (stat.isSymbolicLink()) {
      throw new Error(`payload contains symlink: ${relative}`);
    }
    if (stat.isDirectory()) {
      out.push(...regularFiles(root, relative));
      continue;
    }
    if (!stat.isFile()) {
      throw new Error(`payload contains unsupported entry: ${relative}`);
    }
    out.push(relative);
  }

  return out;
}

export function payloadManifest(root) {
  const packageFile = path.join(root, "package.json");
  if (!fs.existsSync(packageFile) || !fs.statSync(packageFile).isFile()) {
    throw new Error(`package.json missing in ${root}`);
  }

  const files = ["package.json", ...regularFiles(root, "src")].sort();
  const digest = crypto.createHash("sha256");

  for (const relative of files) {
    const absolute = path.join(root, relative);
    digest.update(relative, "utf8");
    digest.update("\0");
    digest.update(fs.readFileSync(absolute));
    digest.update("\0");
  }

  return {
    digest: digest.digest("hex"),
    file_count: files.length
  };
}

export function attestPayload({
  sourceRoot = process.env.RAISE_SOURCE_ROOT ?? defaultSourceRoot,
  installedRoot = process.env.RAISE_INSTALLED_ROOT ?? defaultInstalledRoot
} = {}) {
  const source = payloadManifest(sourceRoot);
  const installed = payloadManifest(installedRoot);
  const ok =
    source.digest === installed.digest &&
    source.file_count === installed.file_count;

  return {
    ok,
    source_digest: source.digest,
    installed_digest: installed.digest,
    source_file_count: source.file_count,
    installed_file_count: installed.file_count,
    reason: ok ? "payload_match" : "payload_mismatch"
  };
}

function writeReport(file, report) {
  if (!file) return;
  fs.mkdirSync(path.dirname(file), { recursive: true });
  fs.writeFileSync(file, JSON.stringify(report, null, 2) + "\n", {
    encoding: "utf8",
    mode: 0o600
  });
  fs.chmodSync(file, 0o600);
}

const isMain =
  process.argv[1] && import.meta.url === pathToFileURL(path.resolve(process.argv[1])).href;

if (isMain) {
  try {
    const report = attestPayload();
    writeReport(process.env.RAISE_PAYLOAD_REPORT ?? "", report);
    console.log(JSON.stringify(report, null, 2));
    process.exit(report.ok ? 0 : 1);
  } catch (error) {
    const report = {
      ok: false,
      reason: "payload_attestation_error",
      error: String(error.message ?? error).slice(0, 300)
    };
    writeReport(process.env.RAISE_PAYLOAD_REPORT ?? "", report);
    console.error(JSON.stringify(report, null, 2));
    process.exit(1);
  }
}
