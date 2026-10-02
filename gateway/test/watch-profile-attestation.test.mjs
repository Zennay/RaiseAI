import assert from "node:assert/strict";
import test from "node:test";
import { attestWatchProfile } from "../deploy/attest-watch-profile.mjs";

function maps({
  url = "https://raise.example:8787",
  token = "t".repeat(64),
  pin = "a".repeat(64),
  port = "8787"
} = {}) {
  return {
    envValues: new Map([
      ["RAISE_PORT", port],
      ["RAISE_GATEWAY_TOKEN", token]
    ]),
    profileValues: new Map([
      ["url", url],
      ["token", token],
      ["spki_sha256", pin]
    ])
  };
}

test("accepts a watch profile bound to gateway token, TLS pin and HTTPS port", () => {
  const values = maps();
  const report = attestWatchProfile({
    ...values,
    certificateSpki: "a".repeat(64),
    certificateHostMatch: true,
    certificateCurrentlyValid: true,
    profileMode: 0o600
  });

  assert.equal(report.ok, true);
  assert.equal(report.reason, "watch_profile_match");
  assert.deepEqual(report.checks, {
    https_url: true,
    port_match: true,
    token_match: true,
    spki_match: true,
    certificate_host_match: true,
    certificate_currently_valid: true,
    profile_mode_600: true
  });
});

test("rejects stale token or pin without serializing either secret", () => {
  const values = maps({ token: "s".repeat(64), pin: "b".repeat(64) });
  values.envValues.set("RAISE_GATEWAY_TOKEN", "t".repeat(64));

  const report = attestWatchProfile({
    ...values,
    certificateSpki: "a".repeat(64),
    certificateHostMatch: true,
    certificateCurrentlyValid: true,
    profileMode: 0o600
  });

  assert.equal(report.ok, false);
  assert.equal(report.checks.token_match, false);
  assert.equal(report.checks.spki_match, false);
  const serialized = JSON.stringify(report);
  assert.equal(serialized.includes("s".repeat(64)), false);
  assert.equal(serialized.includes("t".repeat(64)), false);
  assert.equal(serialized.includes("b".repeat(64)), false);
});

test("rejects insecure URL, host mismatch, expired cert and loose profile mode", () => {
  const values = maps({ url: "http://raise.example:8787" });
  const report = attestWatchProfile({
    ...values,
    certificateSpki: "a".repeat(64),
    certificateHostMatch: false,
    certificateCurrentlyValid: false,
    profileMode: 0o644
  });

  assert.equal(report.ok, false);
  assert.equal(report.checks.https_url, false);
  assert.equal(report.checks.certificate_host_match, false);
  assert.equal(report.checks.certificate_currently_valid, false);
  assert.equal(report.checks.profile_mode_600, false);
});
