#!/usr/bin/env node
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { createHash, timingSafeEqual, X509Certificate } from "node:crypto";
import { pathToFileURL } from "node:url";

function readKeyValueFile(file) {
  const values = new Map();
  for (const line of fs.readFileSync(file, "utf8").split(/\r?\n/)) {
    const index = line.indexOf("=");
    if (index <= 0) continue;
    values.set(line.slice(0, index).trim(), line.slice(index + 1).trim());
  }
  return values;
}

function safeEqual(left, right) {
  const a = Buffer.from(String(left ?? ""));
  const b = Buffer.from(String(right ?? ""));
  return a.length > 0 && a.length === b.length && timingSafeEqual(a, b);
}

export function attestWatchProfile({
  envValues,
  profileValues,
  certificateSpki,
  certificateHostMatch,
  certificateCurrentlyValid,
  profileMode
}) {
  let profileUrl = null;
  try {
    profileUrl = new URL(profileValues.get("url") ?? "");
  } catch {}

  const configuredPort = Number(envValues.get("RAISE_PORT") ?? "");
  const profilePort = profileUrl
    ? Number(profileUrl.port || (profileUrl.protocol === "https:" ? 443 : 80))
    : NaN;

  const profileToken = profileValues.get("token") ?? "";
  const gatewayToken = envValues.get("RAISE_GATEWAY_TOKEN") ?? "";

  const checks = {
    https_url: profileUrl?.protocol === "https:" && Boolean(profileUrl.hostname),
    port_match:
      Number.isInteger(configuredPort) &&
      configuredPort > 0 &&
      profilePort === configuredPort,
    token_match:
      profileToken.length >= 32 &&
      gatewayToken.length >= 32 &&
      safeEqual(profileToken, gatewayToken),
    spki_match:
      /^[a-f0-9]{64}$/i.test(profileValues.get("spki_sha256") ?? "") &&
      safeEqual(profileValues.get("spki_sha256"), certificateSpki),
    certificate_host_match: certificateHostMatch === true,
    certificate_currently_valid: certificateCurrentlyValid === true,
    profile_mode_600: profileMode === 0o600
  };

  const ok = Object.values(checks).every(Boolean);
  return {
    ok,
    reason: ok ? "watch_profile_match" : "watch_profile_mismatch",
    checks
  };
}

function loadAttestation({
  configDir = process.env.RAISE_CONFIG_DIR ?? path.join(os.homedir(), ".config", "raiseai"),
  now = new Date()
} = {}) {
  const envFile = path.join(configDir, "gateway.env");
  const profileFile = path.join(configDir, "watch-gateway.properties");
  const envValues = readKeyValueFile(envFile);
  const profileValues = readKeyValueFile(profileFile);
  const certFile = envValues.get("RAISE_TLS_CERT") ?? "";
  if (!certFile) throw new Error("gateway TLS certificate path is not configured");

  const certificate = new X509Certificate(fs.readFileSync(certFile));
  const spki = createHash("sha256")
    .update(certificate.publicKey.export({ type: "spki", format: "der" }))
    .digest("hex");
  const profileUrl = new URL(profileValues.get("url") ?? "");
  const validFrom = Date.parse(certificate.validFrom);
  const validTo = Date.parse(certificate.validTo);
  const timestamp = now.getTime();

  return attestWatchProfile({
    envValues,
    profileValues,
    certificateSpki: spki,
    certificateHostMatch: Boolean(certificate.checkHost(profileUrl.hostname)),
    certificateCurrentlyValid:
      Number.isFinite(validFrom) &&
      Number.isFinite(validTo) &&
      timestamp >= validFrom &&
      timestamp <= validTo,
    profileMode: fs.statSync(profileFile).mode & 0o777
  });
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
    const report = loadAttestation();
    writeReport(process.env.RAISE_WATCH_PROFILE_REPORT ?? "", report);
    console.log(JSON.stringify(report, null, 2));
    process.exit(report.ok ? 0 : 1);
  } catch {
    const report = {
      ok: false,
      reason: "watch_profile_attestation_error",
      checks: {}
    };
    writeReport(process.env.RAISE_WATCH_PROFILE_REPORT ?? "", report);
    console.error(JSON.stringify(report, null, 2));
    process.exit(1);
  }
}
