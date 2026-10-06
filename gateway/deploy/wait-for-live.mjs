#!/usr/bin/env node
// Revision-aware readiness gate for the deployed Raise gateway.
//
// This is intentionally unauthenticated and secret-safe: it only polls /health,
// verifies the exact expected revision, and optionally writes a 0600 JSON report.
import fs from "node:fs";
import https from "node:https";
import os from "node:os";
import path from "node:path";
import { httpsOrigin, positiveInteger } from "./readiness-config.mjs";
import { evaluateReadinessHttpResponse } from "./readiness-http.mjs";

const configDir =
  process.env.RAISE_CONFIG_DIR ?? path.join(os.homedir(), ".config", "raiseai");

function readKeyValueFile(file) {
  const out = new Map();
  if (!fs.existsSync(file)) return out;
  for (const line of fs.readFileSync(file, "utf8").split("\n")) {
    const idx = line.indexOf("=");
    if (idx > 0) out.set(line.slice(0, idx).trim(), line.slice(idx + 1).trim());
  }
  return out;
}


const env = readKeyValueFile(path.join(configDir, "gateway.env"));
const profile = readKeyValueFile(
  path.join(configDir, "watch-gateway.properties")
);

const baseUrl = httpsOrigin(
  process.env.RAISE_READY_URL ??
    process.env.RAISE_SMOKE_URL ??
    profile.get("url") ??
    "",
  "Raise readiness URL"
);
const certFile = env.get("RAISE_TLS_CERT") ?? "";
const expectedRevision =
  process.env.RAISE_EXPECTED_REVISION ??
  env.get("RAISE_DEPLOY_REVISION") ??
  "";
const timeoutMs = positiveInteger(process.env.RAISE_READY_TIMEOUT_MS, 30_000);
const intervalMs = positiveInteger(process.env.RAISE_READY_INTERVAL_MS, 500);
const reportPath = process.env.RAISE_READY_REPORT ?? "";

if (!certFile) throw new Error("RAISE_TLS_CERT not configured");
if (!expectedRevision) throw new Error("expected deploy revision missing");

const ca = fs.readFileSync(certFile);
const startedAt = Date.now();
const deadline = startedAt + timeoutMs;
let attempts = 0;
let last = {
  ok: false,
  reason: "not_attempted",
  revision: null
};

function writeReport(report) {
  if (!reportPath) return;
  fs.mkdirSync(path.dirname(reportPath), { recursive: true });
  fs.writeFileSync(reportPath, JSON.stringify(report, null, 2) + "\n", {
    encoding: "utf8",
    mode: 0o600
  });
  fs.chmodSync(reportPath, 0o600);
}

function requestHealth() {
  return new Promise((resolve, reject) => {
    const req = https.request(
      {
        method: "GET",
        host: baseUrl.hostname,
        port: baseUrl.port || 443,
        path: "/health",
        ca,
        timeout: Math.min(5_000, timeoutMs)
      },
      res => {
        const chunks = [];
        res.on("data", chunk => chunks.push(chunk));
        res.on("end", () => {
          let json = null;
          try {
            json = JSON.parse(Buffer.concat(chunks).toString("utf8"));
          } catch {}
          resolve({ status: res.statusCode, json, contentType: res.headers["content-type"] });
        });
      }
    );
    req.on("timeout", () => req.destroy(new Error("timeout")));
    req.on("error", reject);
    req.end();
  });
}

while (Date.now() <= deadline) {
  attempts += 1;
  try {
    const response = await requestHealth();
    last = evaluateReadinessHttpResponse({
      ...response,
      expectedRevision
    });
  } catch (error) {
    last = {
      ok: false,
      reason: "health_unreachable",
      revision: null,
      error: String(error.message ?? error).slice(0, 300)
    };
  }

  if (last.ok) {
    const report = {
      ok: true,
      host: baseUrl.hostname,
      expected_revision: expectedRevision,
      live_revision: last.revision,
      attempts,
      elapsed_ms: Date.now() - startedAt,
      reason: last.reason
    };
    writeReport(report);
    console.log(JSON.stringify(report, null, 2));
    process.exit(0);
  }

  const remaining = deadline - Date.now();
  if (remaining <= 0) break;
  await new Promise(resolve => setTimeout(resolve, Math.min(intervalMs, remaining)));
}

const report = {
  ok: false,
  host: baseUrl.hostname,
  expected_revision: expectedRevision,
  live_revision: last.revision ?? null,
  attempts,
  elapsed_ms: Date.now() - startedAt,
  reason: last.reason,
  ...(last.error ? { error: last.error } : {})
};
writeReport(report);
console.error(JSON.stringify(report, null, 2));
process.exit(1);
