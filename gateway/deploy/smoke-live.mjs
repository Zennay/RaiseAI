#!/usr/bin/env node
// Live smoke test for the deployed Raise gateway (run on the VPS).
//
// Only exercises paths WITHOUT side effects:
//   - GET /health
//   - unauthenticated request is rejected (401)
//   - authenticated zcloud_task request for a *custom* task, which the zCloud
//     connector must refuse ("zcloud_custom_task_not_supported") without
//     queueing anything. This proves the live gateway -> zCloud connector wiring
//     (GET /api/runner-targets reachable, project resolved) without starting
//     or pushing any project.
//
// The gateway token is read from the local env file and is never printed.
import fs from "node:fs";
import https from "node:https";
import os from "node:os";
import path from "node:path";

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

if (token.length < 32) throw new Error("gateway token missing or too short");
if (!certFile) throw new Error("RAISE_TLS_CERT not configured");

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

await check("health", async () => {
  const { status, json } = await request("GET", "/health");
  expect(status === 200 && json?.ok === true, `unexpected health ${status}`);
  return { status };
});

await check("unauthenticated_rejected", async () => {
  const { status } = await request("POST", "/v1/assistant", {
    body: { text: "hallo" }
  });
  expect(status === 401, `expected 401, got ${status}`);
  return { status };
});

function sleep(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

await check("zcloud_connector_custom_task_refused", async () => {
  // zCloud's local API (port 8765) restarts periodically (self-heal probe),
  // which briefly surfaces as reason "zcloud_unavailable" from the connector.
  // Retry only that specific transient condition so a momentary zCloud
  // restart doesn't fail an otherwise-healthy gateway deploy; any other
  // reason/status still fails immediately on the first attempt.
  const maxAttempts = 4;
  let status, json;
  for (let attempt = 1; attempt <= maxAttempts; attempt++) {
    ({ status, json } = await request("POST", "/v1/assistant", {
      auth: true,
      body: { text: "Ga door met Raise AI en fix de zaak" }
    }));
    const transient = status === 200 && json?.execution?.reason === "zcloud_unavailable";
    if (transient && attempt < maxAttempts) {
      await sleep(2_000);
      continue;
    }
    break;
  }
  expect(status === 200, `expected 200, got ${status}`);
  expect(json?.route === "zcloud_task", `route was ${json?.route}`);
  expect(
    json?.execution?.reason === "zcloud_custom_task_not_supported",
    `reason was ${json?.execution?.reason}`
  );
  expect(json?.execution?.provider === "zcloud", "provider was not zcloud");
  return { status, route: json.route, reason: json.execution.reason };
});

const ok = checks.every(item => item.ok);
console.log(JSON.stringify({ ok, host: baseUrl.hostname, checks }, null, 2));
process.exit(ok ? 0 : 1);
