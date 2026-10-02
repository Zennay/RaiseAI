import assert from "node:assert/strict";
import test from "node:test";
import { attestRuntimeWiring } from "../deploy/attest-runtime-wiring.mjs";

const home = "/home/ubuntu";
const installDir = home + "/.local/share/raise-gateway";
const envFile = home + "/.config/raiseai/gateway.env";
const unitFile = home + "/.config/systemd/user/raise-gateway.service";
const serverFile = installDir + "/src/server.mjs";

function healthySystemctl() {
  return [
    "FragmentPath=" + unitFile,
    "WorkingDirectory=" + installDir,
    "ExecStart={ path=/usr/bin/node ; argv[]=/usr/bin/node " + serverFile + " ; ignore_errors=no ; start_time=[n/a] ; stop_time=[n/a] ; pid=0 ; code=(null) ; status=0/0 }",
    "EnvironmentFiles=" + envFile + " (ignore_errors=no)",
    "ActiveState=active",
    "SubState=running"
  ].join("\n");
}

test("accepts the exact loaded Raise gateway runtime wiring", () => {
  const report = attestRuntimeWiring({ systemctlOutput: healthySystemctl(), home });
  assert.equal(report.ok, true);
  assert.equal(report.reason, "runtime_wiring_match");
  assert.deepEqual(report.checks, {
    fragment_path: true,
    working_directory: true,
    exec_start: true,
    environment_file: true
  });
  assert.equal(report.active_state, "active");
  assert.equal(report.sub_state, "running");
});

test("rejects a stale or miswired loaded systemd service", () => {
  const stale = healthySystemctl()
    .replace(serverFile, home + "/old/server.mjs")
    .replace(envFile, home + "/old/gateway.env");

  const report = attestRuntimeWiring({ systemctlOutput: stale, home });
  assert.equal(report.ok, false);
  assert.equal(report.reason, "runtime_wiring_mismatch");
  assert.equal(report.checks.exec_start, false);
  assert.equal(report.checks.environment_file, false);
});

test("rejects an inactive service even when paths are correct", () => {
  const report = attestRuntimeWiring({
    systemctlOutput: healthySystemctl()
      .replace("ActiveState=active", "ActiveState=failed")
      .replace("SubState=running", "SubState=dead"),
    home
  });
  assert.equal(report.ok, false);
  assert.equal(report.active_state, "failed");
  assert.equal(report.sub_state, "dead");
});

test("report contains no environment-file contents or provider secrets", () => {
  const report = attestRuntimeWiring({ systemctlOutput: healthySystemctl(), home });
  const serialized = JSON.stringify(report);
  assert.equal(serialized.includes("OPENROUTER_API_KEY"), false);
  assert.equal(serialized.includes("RAISE_GATEWAY_TOKEN"), false);
  assert.equal(serialized.includes("EnvironmentFiles"), false);
});
