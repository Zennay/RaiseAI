#!/usr/bin/env node
// Live smoke test for the deployed Raise gateway (run on the VPS).
//
// Hard deploy gates:
//   - GET /health is healthy and serves the exact expected revision;
//   - unauthenticated assistant requests are rejected (401).
//
// Dependency probes:
//   - when OPENROUTER_API_KEY exists in the VPS env, one authenticated quick_ai
//     request must return a real OpenRouter answer;
//   - when the key is absent, that exact missing-credential state is recorded as
//     degraded evidence without failing an otherwise healthy gateway deploy;
//   - authenticated custom zCloud task must route to the zCloud connector;
//   - normal refusal proves the connector is reachable;
//   - zcloud_unavailable is reported as degraded but does not fail a gateway
//     deployment unless RAISE_REQUIRE_ZCLOUD=1 is explicitly requested.
//
// The gateway token is read from the local env file and is never printed.
import fs from "node:fs";
import https from "node:https";
import os from "node:os";
import path from "node:path";
import { evaluateZCloudProbe } from "./smoke-policy.mjs";

const configDir =
  process.env.RAISE_CONFIG_DIR ?? path.join(os.homedir(), ".config", "raiseai");

function readKeyValueFile(file) {
  const out = new Map();
  for (const line of fs.readFileSync(file, "utf8").split("\n")) {
    const idx = line.indexOf("=");
    if (idx > 0) out.set(line.slice(0, idx).trim(), line.slice(idx + 1).trim());
  }
  return out;
}

const env = readKeyValueFile(path.join(configDir, "gateway.env"));
const profile = readKeyValueFile(path.join(configDir, "watch-gateway.properties"));

const token = env.get("RAISE_GATEWAY_TOKEN") ?? "";
const baseUrl = new URL(process.env.RAISE_SMOKE_URL ?? profile.get("url") ?? "");
const certFile = env.get("RAISE_TLS_CERT") ?? "";
const expectedRevision =
  process.env.RAISE_EXPECTED_REVISION ?? env.get("RAISE_DEPLOY_REVISION") ?? "";
const requireZCloud = process.env.RAISE_REQUIRE_ZCLOUD === "1";
const openRouterConfigured = Boolean(env.get("OPENROUTER_API_KEY"));

if (token.length < 32) throw new Error("gateway token missing or too short");
if (!certFile) throw new Error("RAISE_TLS_CERT not configured");
if (!expectedRevision) throw new Error("expected deploy revision missing");

const ca = fs.readFileSync(certFile);

function request(method, route, { auth = false, body = null } = {}) {
  return new Promise((resolve, reject) => {
    const payload = body ? Buffer.from(JSON.stringify(body)) : null;
    const headers = {};
    if (payload) {
      headers["content-type"] = "application/json";
      headers["content-length"] = payload.length;
    }
    if (auth) headers.authorization = "Bearer " + token;

    const req = https.request(
      {
        method,
        host: baseUrl.hostname,
        port: baseUrl.port || 443,
        path: route,
        headers,
        ca,
        timeout: 10_000
      },
      res => {
        const chunks = [];
        res.on("data", chunk => chunks.push(chunk));
        res.on("end", () => {
          let json = null;
          try {
            json = JSON.parse(Buffer.concat(chunks).toString("utf8"));
          } catch {}
          resolve({ status: res.statusCode, json });
        });
      }
    );
    req.on("timeout", () => req.destroy(new Error("timeout")));
    req.on("error", reject);
    if (payload) req.write(payload);
    req.end();
  });
}

const checks = [];
async function check(name, fn) {
  try {
    const detail = await fn();
    checks.push({ name, ok: true, ...detail });
  } catch (error) {
    checks.push({ name, ok: false, error: String(error.message ?? error) });
  }
}

function expect(condition, message) {
  if (!condition) throw new Error(message);
}

await check("health_revision", async () => {
  const { status, json } = await request("GET", "/health");
  expect(status === 200 && json?.ok === true, `unexpected health ${status}`);
  expect(
    json?.revision === expectedRevision,
    `live revision ${json?.revision ?? "missing"} != expected ${expectedRevision}`
  );
  return { status, revision: json.revision };
});

await check("unauthenticated_rejected", async () => {
  const { status } = await request("POST", "/v1/assistant", {
    body: { text: "hallo" }
  });
  expect(status === 401, `expected 401, got ${status}`);
  return { status };
});

await check("openrouter_quick_ai_probe", async () => {
  if (!openRouterConfigured) {
    return {
      route: "quick_ai",
      configured: false,
      reason: "openrouter_not_configured",
      degraded: true
    };
  }

  const { status, json } = await request("POST", "/v1/assistant", {
    auth: true,
    body: { text: "Antwoord met één kort woord: gereed" }
  });

  expect(status === 200, `expected provider status 200, got ${status}`);
  expect(json?.route === "quick_ai", `expected quick_ai route, got ${json?.route ?? "missing"}`);
  expect(json?.execution?.enabled === true, "OpenRouter execution was not enabled");
  expect(json?.execution?.provider === "openrouter", `unexpected provider ${json?.execution?.provider ?? "missing"}`);
  expect(
    typeof json?.answer === "string" && json.answer.trim().length > 0,
    "OpenRouter returned no answer"
  );

  return {
    status,
    route: json.route,
    configured: true,
    provider: json.execution.provider,
    model: json.execution.model ?? null
  };
});

await check("zcloud_dependency_probe", async () => {
  const { status, json } = await request("POST", "/v1/assistant", {
    auth: true,
    body: { text: "Ga door met Raise AI en fix de zaak" }
  });

  const result = evaluateZCloudProbe({
    status,
    json,
    requireZCloud
  });

  expect(result.ok, `zCloud dependency probe failed: ${result.reason}`);
  return {
    status,
    route: json?.route ?? null,
    reason: result.reason,
    degraded: result.degraded
  };
});

const ok = checks.every(item => item.ok);
const degraded = checks.some(item => item.degraded === true);
const report = {
  ok,
  degraded,
  host: baseUrl.hostname,
  expected_revision: expectedRevision,
  checks
};

const reportPath = process.env.RAISE_SMOKE_REPORT ?? "";
if (reportPath) {
  fs.mkdirSync(path.dirname(reportPath), { recursive: true });
  fs.writeFileSync(reportPath, JSON.stringify(report, null, 2) + "\n", {
    encoding: "utf8",
    mode: 0o600
  });
  fs.chmodSync(reportPath, 0o600);
}

console.log(JSON.stringify(report, null, 2));
process.exit(ok ? 0 : 1);
