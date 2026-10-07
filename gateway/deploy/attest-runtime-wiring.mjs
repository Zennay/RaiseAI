#!/usr/bin/env node
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { execFileSync } from "node:child_process";
import { pathToFileURL } from "node:url";

function parseProperties(output) {
  const properties = {};
  for (const line of String(output ?? "").split(/\r?\n/)) {
    const index = line.indexOf("=");
    if (index <= 0) continue;
    properties[line.slice(0, index)] = line.slice(index + 1);
  }
  return properties;
}

function expectedPaths(home) {
  const installDir = path.join(home, ".local", "share", "raise-gateway");
  return {
    unitFile: path.join(home, ".config", "systemd", "user", "raise-gateway.service"),
    installDir,
    envFile: path.join(home, ".config", "raiseai", "gateway.env"),
    serverFile: path.join(installDir, "src", "server.mjs")
  };
}

export function attestRuntimeWiring({
  systemctlOutput,
  home = process.env.HOME ?? os.homedir()
} = {}) {
  const expected = expectedPaths(home);
  const properties = parseProperties(systemctlOutput);
  const execStart = properties.ExecStart ?? "";
  const environmentFiles = properties.EnvironmentFiles ?? "";

  const checks = {
    fragment_path: properties.FragmentPath === expected.unitFile,
    working_directory: properties.WorkingDirectory === expected.installDir,
    exec_start:
      execStart.includes("path=/usr/bin/node") &&
      execStart.includes(expected.serverFile),
    environment_file: environmentFiles.includes(expected.envFile),
    no_new_privileges: properties.NoNewPrivileges === "yes",
    private_tmp: properties.PrivateTmp === "yes",
    protect_system: properties.ProtectSystem === "strict"
  };

  const activeState = properties.ActiveState ?? null;
  const subState = properties.SubState ?? null;
  const ok =
    Object.values(checks).every(Boolean) &&
    activeState === "active" &&
    subState === "running";

  return {
    ok,
    reason: ok ? "runtime_wiring_match" : "runtime_wiring_mismatch",
    active_state: activeState,
    sub_state: subState,
    checks
  };
}

export function userSystemdEnvironment({
  env = process.env,
  uid = typeof process.getuid === "function" ? process.getuid() : null,
  exists = fs.existsSync
} = {}) {
  const next = { ...env };
  const runtimeDir =
    env.XDG_RUNTIME_DIR ||
    (Number.isInteger(uid) ? `/run/user/${uid}` : "");

  if (runtimeDir) next.XDG_RUNTIME_DIR = runtimeDir;

  const busAddress =
    env.DBUS_SESSION_BUS_ADDRESS ||
    (runtimeDir && exists(path.join(runtimeDir, "bus"))
      ? `unix:path=${runtimeDir}/bus`
      : "");

  if (busAddress) next.DBUS_SESSION_BUS_ADDRESS = busAddress;
  return next;
}

function systemctlShow() {
  return execFileSync(
    "systemctl",
    [
      "--user",
      "show",
      "raise-gateway.service",
      "--property=FragmentPath",
      "--property=WorkingDirectory",
      "--property=ExecStart",
      "--property=EnvironmentFiles",
      "--property=NoNewPrivileges",
      "--property=PrivateTmp",
      "--property=ProtectSystem",
      "--property=ActiveState",
      "--property=SubState",
      "--no-pager"
    ],
    {
      encoding: "utf8",
      stdio: ["ignore", "pipe", "pipe"],
      env: userSystemdEnvironment()
    }
  );
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
    const report = attestRuntimeWiring({ systemctlOutput: systemctlShow() });
    writeReport(process.env.RAISE_RUNTIME_REPORT ?? "", report);
    console.log(JSON.stringify(report, null, 2));
    process.exit(report.ok ? 0 : 1);
  } catch (error) {
    const report = {
      ok: false,
      reason: "runtime_wiring_attestation_error",
      error: String(error.message ?? error).slice(0, 300)
    };
    writeReport(process.env.RAISE_RUNTIME_REPORT ?? "", report);
    console.error(JSON.stringify(report, null, 2));
    process.exit(1);
  }
}
