import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import { spawnSync } from "node:child_process";

const here = dirname(fileURLToPath(import.meta.url));
const gatewayRoot = join(here, "..");
const policy = join(gatewayRoot, "deploy", "token-policy.sh");
const installer = join(gatewayRoot, "deploy", "install-user-gateway.sh");

function tokenIsValid(token) {
  const result = spawnSync(
    "bash",
    ["-c", 'source "$1"; raise_gateway_token_is_valid "$2"', "bash", policy, token],
    { encoding: "utf8" }
  );
  return result.status === 0;
}

test("deploy token policy matches gateway runtime safety boundary", () => {
  assert.equal(tokenIsValid("x".repeat(31)), false);
  assert.equal(tokenIsValid("x".repeat(32)), true);
  assert.equal(tokenIsValid("A1-._~".repeat(6)), true);

  for (const token of [
    "x".repeat(32) + " ",
    "x".repeat(16) + "\t" + "y".repeat(16),
    "x".repeat(16) + "\n" + "y".repeat(16),
    "x".repeat(16) + "\r" + "y".repeat(16),
    "x".repeat(16) + String.fromCharCode(127) + "y".repeat(16)
  ]) {
    assert.equal(tokenIsValid(token), false, JSON.stringify(token));
  }
});

test("installer applies token policy before deciding whether to rotate", () => {
  const source = readFileSync(installer, "utf8");
  assert.match(source, /source "\$SCRIPT_DIR\/token-policy\.sh"/);
  assert.match(source, /if ! raise_gateway_token_is_valid "\$TOKEN"; then/);
  assert.match(source, /TOKEN="\$\(openssl rand -hex 32\)"/);
});
