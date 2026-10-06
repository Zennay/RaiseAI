import assert from "node:assert/strict";
import test from "node:test";
import {
  attestRuntimeWiring,
  userSystemdEnvironment
} from "../deploy/attest-runtime-wiring.mjs";

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

test("rejects prefix-spoofed runtime paths and executable names", () => {
  const spoofedPaths = healthySystemctl()
    .replace(serverFile + " ;", serverFile + ".old ;")
    .replace(envFile + " (ignore_errors=no)", envFile + ".bak (ignore_errors=no)");

  const pathReport = attestRuntimeWiring({
    systemctlOutput: spoofedPaths,
    home
  });
  assert.equal(pathReport.ok, false);
  assert.equal(pathReport.checks.exec_start, false);
  assert.equal(pathReport.checks.environment_file, false);

  const spoofedBinary = healthySystemctl()
    .replace("path=/usr/bin/node ;", "path=/usr/bin/node-wrapper ;")
    .replace("argv[]=/usr/bin/node ", "argv[]=/usr/bin/node-wrapper ");

  const binaryReport = attestRuntimeWiring({
    systemctlOutput: spoofedBinary,
    home
  });
  assert.equal(binaryReport.ok, false);
  assert.equal(binaryReport.checks.exec_start, false);
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


test("derives the user systemd bus for headless runners", () => {
  const env = userSystemdEnvironment({
    env: { HOME: home },
    uid: 1000,
    exists: value => value === "/run/user/1000/bus"
  });

  assert.equal(env.XDG_RUNTIME_DIR, "/run/user/1000");
  assert.equal(env.DBUS_SESSION_BUS_ADDRESS, "unix:path=/run/user/1000/bus");
});

test("preserves an explicitly configured user systemd bus", () => {
  const env = userSystemdEnvironment({
    env: {
      XDG_RUNTIME_DIR: "/custom/runtime",
      DBUS_SESSION_BUS_ADDRESS: "unix:path=/custom/bus"
    },
    uid: 1000,
    exists: () => false
  });

  assert.equal(env.XDG_RUNTIME_DIR, "/custom/runtime");
  assert.equal(env.DBUS_SESSION_BUS_ADDRESS, "unix:path=/custom/bus");
});
