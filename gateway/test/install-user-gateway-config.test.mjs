import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { spawnSync } from "node:child_process";

const testDir = path.dirname(fileURLToPath(import.meta.url));
const installer = path.resolve(testDir, "../deploy/install-user-gateway.sh");

function runInvalidConfig(overrides) {
  const home = fs.mkdtempSync(path.join(os.tmpdir(), "raise-installer-config-"));
  try {
    const result = spawnSync("bash", [installer], {
      encoding: "utf8",
      env: {
        ...process.env,
        HOME: home,
        RAISE_DEPLOY_REVISION: "a".repeat(40),
        RAISE_PUBLIC_HOST: "raise.example",
        RAISE_PUBLIC_PORT: "8787",
        ...overrides
      }
    });
    return {
      status: result.status,
      stderr: result.stderr,
      configCreated: fs.existsSync(path.join(home, ".config", "raiseai"))
    };
  } finally {
    fs.rmSync(home, { recursive: true, force: true });
  }
}


function writeExecutable(file, content) {
  fs.writeFileSync(file, content, { mode: 0o755 });
}

function permissionMode(file) {
  return fs.existsSync(file) ? fs.statSync(file).mode & 0o777 : null;
}

function runInstallerWithShadowedDependency(dependency) {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "raise-installer-dependency-"));
  const home = path.join(root, "home");
  const bin = path.join(root, "bin");
  const bashEnv = path.join(root, "bash-env");
  fs.mkdirSync(home);
  fs.mkdirSync(bin);

  writeExecutable(
    path.join(bin, "node"),
    `#!/usr/bin/env bash
if [ "\${1:-}" = "-p" ]; then
  printf '%s\\n' '22'
  exit 0
fi
exit 0
`
  );
  fs.writeFileSync(
    bashEnv,
    `${dependency}() { :; }\n`,
    "utf8"
  );

  try {
    const result = spawnSync("/bin/bash", [installer], {
      encoding: "utf8",
      env: {
        ...process.env,
        BASH_ENV: bashEnv,
        HOME: home,
        PATH: bin + path.delimiter + process.env.PATH,
        RAISE_DEPLOY_REVISION: "a".repeat(40),
        RAISE_PUBLIC_HOST: "raise.example",
        RAISE_PUBLIC_PORT: "8787"
      }
    });
    return {
      status: result.status,
      stderr: result.stderr,
      configCreated: fs.existsSync(path.join(home, ".config", "raiseai")),
      installCreated: fs.existsSync(path.join(home, ".local", "share", "raise-gateway"))
    };
  } finally {
    fs.rmSync(root, { recursive: true, force: true });
  }
}

function runInstallerWithStubbedRuntime(host, { configDir, existingToken, nodeMajor = "22" } = {}) {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "raise-installer-san-"));
  const home = path.join(root, "home");
  const bin = path.join(root, "bin");
  const opensslLog = path.join(root, "openssl.log");
  fs.mkdirSync(home);
  fs.mkdirSync(bin);

  const effectiveConfigDir =
    configDir ?? path.join(home, ".config", "raiseai");
  if (existingToken !== undefined) {
    fs.mkdirSync(effectiveConfigDir, { recursive: true });
    fs.writeFileSync(
      path.join(effectiveConfigDir, "gateway.env"),
      `RAISE_GATEWAY_TOKEN=${existingToken}\n`
    );
  }

  writeExecutable(
    path.join(bin, "openssl"),
    `#!/usr/bin/env bash
set -euo pipefail
case "\${1:-}" in
  rand)
    printf '%s\\n' 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa'
    ;;
  req)
    printf '%s\\n' "$*" >> "$OPENSSL_LOG"
    key=''
    cert=''
    while [ "$#" -gt 0 ]; do
      case "$1" in
        -keyout) key="$2"; shift 2 ;;
        -out) cert="$2"; shift 2 ;;
        *) shift ;;
      esac
    done
    printf 'fake-key\\n' > "$key"
    printf 'fake-cert\\n' > "$cert"
    ;;
  x509)
    printf 'fake-public-key\\n'
    ;;
  pkey)
    cat
    ;;
  dgst)
    cat >/dev/null
    printf '%s\\n' 'SHA2-256(stdin)= bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb'
    ;;
  *)
    exit 2
    ;;
esac
`
  );
  writeExecutable(path.join(bin, "systemctl"), "#!/usr/bin/env bash\nexit 0\n");
  writeExecutable(
    path.join(bin, "node"),
    `#!/usr/bin/env bash
set -euo pipefail
if [ "\${1:-}" = "-p" ]; then
  printf '%s\\n' "\${FAKE_NODE_MAJOR-22}"
  exit 0
fi
exit 0
`
  );

  try {
    const result = spawnSync("bash", [installer], {
      encoding: "utf8",
      env: {
        ...process.env,
        HOME: home,
        PATH: bin + path.delimiter + process.env.PATH,
        OPENSSL_LOG: opensslLog,
        FAKE_NODE_MAJOR: nodeMajor,
        RAISE_DEPLOY_REVISION: "a".repeat(40),
        RAISE_PUBLIC_HOST: host,
        RAISE_PUBLIC_PORT: "8787",
        ...(configDir ? { RAISE_CONFIG_DIR: configDir } : {})
      }
    });
    const envPath = path.join(effectiveConfigDir, "gateway.env");
    const envText = fs.existsSync(envPath) ? fs.readFileSync(envPath, "utf8") : "";
    const gatewayToken =
      envText.match(/^RAISE_GATEWAY_TOKEN=(.*)$/m)?.[1] ?? null;
    const installDir = path.join(home, ".local", "share", "raise-gateway");
    const unitPath = path.join(home, ".config", "systemd", "user", "raise-gateway.service");
    return {
      status: result.status,
      stderr: result.stderr,
      opensslLog: fs.existsSync(opensslLog)
        ? fs.readFileSync(opensslLog, "utf8")
        : "",
      configDir: effectiveConfigDir,
      installDir,
      nodePath: path.join(bin, "node"),
      unitText: fs.existsSync(unitPath) ? fs.readFileSync(unitPath, "utf8") : "",
      permissions: {
        configDir: permissionMode(effectiveConfigDir),
        tlsDir: permissionMode(path.join(effectiveConfigDir, "tls")),
        envFile: permissionMode(envPath),
        privateKey: permissionMode(path.join(effectiveConfigDir, "tls", "gateway-key.pem")),
        certificate: permissionMode(path.join(effectiveConfigDir, "tls", "gateway-cert.pem")),
        watchProfile: permissionMode(
          path.join(effectiveConfigDir, "watch-gateway.properties")
        )
      },
      envCreated: fs.existsSync(envPath),
      gatewayToken,
      profileCreated: fs.existsSync(
        path.join(effectiveConfigDir, "watch-gateway.properties")
      ),
      defaultConfigCreated: fs.existsSync(
        path.join(home, ".config", "raiseai", "gateway.env")
      )
    };
  } finally {
    fs.rmSync(root, { recursive: true, force: true });
  }
}

test("installer requires deploy dependencies before filesystem mutation", () => {
  for (const dependency of ["openssl", "systemctl"]) {
    const result = runInstallerWithShadowedDependency(dependency);
    assert.notEqual(result.status, 0, dependency);
    assert.match(
      result.stderr,
      new RegExp(`absolute executable ${dependency} binary`),
      dependency
    );
    assert.equal(result.configCreated, false, dependency);
    assert.equal(result.installCreated, false, dependency);
  }
});

test("installer requires Node.js 22+ before deployment side effects", () => {
  for (const nodeMajor of ["", "not-a-number", "0", "21"]) {
    const result = runInstallerWithStubbedRuntime("raise.example", { nodeMajor });
    assert.notEqual(result.status, 0, JSON.stringify(nodeMajor));
    assert.match(result.stderr, /Raise gateway requires Node\.js >= 22/);
    assert.equal(result.envCreated, false, JSON.stringify(nodeMajor));
    assert.equal(result.profileCreated, false, JSON.stringify(nodeMajor));
    assert.equal(result.opensslLog, "", JSON.stringify(nodeMajor));
  }

  for (const nodeMajor of ["22", "24"]) {
    const result = runInstallerWithStubbedRuntime("raise.example", { nodeMajor });
    assert.equal(result.status, 0, result.stderr);
    assert.equal(result.envCreated, true);
    assert.equal(result.profileCreated, true);
  }
});

test("installer Node floor stays aligned with package engine contract", () => {
  const packageJson = JSON.parse(
    fs.readFileSync(path.resolve(testDir, "../package.json"), "utf8")
  );
  const installerText = fs.readFileSync(installer, "utf8");
  assert.equal(packageJson.engines?.node, ">=22");
  assert.match(installerText, /^NODE_MIN_MAJOR=22$/m);
  assert.match(installerText, /ExecStart=\$NODE_BIN \$INSTALL_DIR\/src\/server\.mjs/);
  assert.match(installerText, /"\$NODE_BIN" "\$SCRIPT_DIR\/wait-for-live\.mjs"/);
  assert.match(installerText, /OPENSSL_BIN="\$\(resolve_dependency openssl\)"/);
  assert.match(installerText, /SYSTEMCTL_BIN="\$\(resolve_dependency systemctl\)"/);
  assert.match(installerText, /"\$OPENSSL_BIN" rand -hex 32/);
  assert.match(installerText, /"\$SYSTEMCTL_BIN" --user restart raise-gateway\.service/);
});

test("installer emits a hardened user service contract", () => {
  const result = runInstallerWithStubbedRuntime("raise.example");
  assert.equal(result.status, 0, result.stderr);
  assert.ok(result.unitText, "installer must write the user service unit");

  const lines = result.unitText.trimEnd().split("\n");
  for (const directive of [
    "After=network-online.target",
    "Wants=network-online.target",
    "Type=simple",
    "Restart=on-failure",
    "RestartSec=2",
    "NoNewPrivileges=true",
    "PrivateTmp=true",
    "ProtectSystem=strict",
    "WantedBy=default.target"
  ]) {
    assert.equal(
      lines.filter((line) => line === directive).length,
      1,
      `expected exactly one ${directive}`
    );
  }

  assert.ok(result.unitText.includes(`WorkingDirectory=${result.installDir}\n`));
  assert.ok(
    result.unitText.includes(
      `EnvironmentFile=${path.join(result.configDir, "gateway.env")}\n`
    )
  );
  assert.ok(
    result.unitText.includes(
      `ExecStart=${result.nodePath} ${path.join(result.installDir, "src", "server.mjs")}\n`
    )
  );
  assert.equal(lines.some((line) => line.startsWith("User=")), false);
  assert.equal(lines.some((line) => line.startsWith("Environment=")), false);
});

test("installer keeps gateway credentials private on disk", () => {
  const result = runInstallerWithStubbedRuntime("raise.example");
  assert.equal(result.status, 0, result.stderr);
  assert.deepEqual(result.permissions, {
    configDir: 0o700,
    tlsDir: 0o700,
    envFile: 0o600,
    privateKey: 0o600,
    certificate: 0o644,
    watchProfile: 0o600
  });
});

test("installer uses a certificate SAN matching the public host identity", () => {
  for (const [host, expectedSan] of [
    ["raise.example", "subjectAltName=DNS:raise.example"],
    ["192.0.2.10", "subjectAltName=IP:192.0.2.10"]
  ]) {
    const result = runInstallerWithStubbedRuntime(host);
    assert.equal(result.status, 0, result.stderr);
    assert.ok(result.opensslLog.includes(expectedSan), result.opensslLog);
  }
});

test("installer preserves only gateway tokens accepted by the server contract", () => {
  const safeToken = "s".repeat(40);
  const safe = runInstallerWithStubbedRuntime("raise.example", {
    existingToken: safeToken
  });
  assert.equal(safe.status, 0, safe.stderr);
  assert.equal(safe.gatewayToken, safeToken);

  for (const invalidToken of [
    "x".repeat(31),
    "x".repeat(32) + " bad",
    "x".repeat(32) + "\tbad"
  ]) {
    const repaired = runInstallerWithStubbedRuntime("raise.example", {
      existingToken: invalidToken
    });
    assert.equal(repaired.status, 0, repaired.stderr);
    assert.equal(repaired.gatewayToken, "a".repeat(64));
  }
});

test("installer honors RAISE_CONFIG_DIR across generated deployment state", () => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "raise-custom-config-"));
  try {
    const configDir = path.join(root, "raise-config");
    const result = runInstallerWithStubbedRuntime("raise.example", { configDir });
    assert.equal(result.status, 0, result.stderr);
    assert.equal(result.configDir, configDir);
    assert.equal(result.envCreated, true);
    assert.equal(result.profileCreated, true);
    assert.equal(result.defaultConfigCreated, false);
  } finally {
    fs.rmSync(root, { recursive: true, force: true });
  }
});

test("installer rejects malformed public hosts before side effects", () => {
  for (const host of [
    " raise.example",
    "raise.example ",
    "raise..example",
    ".raise.example",
    "raise.example.",
    "-raise.example",
    "raise-.example",
    "raise/example",
    "raise:443",
    "raise\nexample",
    "raise\texample",
    "raise\rexample",
    "a".repeat(64) + ".example",
    "a".repeat(254)
  ]) {
    const result = runInvalidConfig({ RAISE_PUBLIC_HOST: host });
    assert.notEqual(result.status, 0, JSON.stringify(host));
    assert.match(result.stderr, /Invalid RAISE_PUBLIC_HOST/, JSON.stringify(host));
    assert.equal(result.configCreated, false, JSON.stringify(host));
  }
});

test("installer rejects malformed public ports before side effects", () => {
  for (const port of [
    "0",
    "00080",
    "65536",
    " 8787",
    "8787 ",
    "+8787",
    "-1",
    "1e3",
    "8787.0",
    "443\n8443"
  ]) {
    const result = runInvalidConfig({ RAISE_PUBLIC_PORT: port });
    assert.notEqual(result.status, 0, JSON.stringify(port));
    assert.match(result.stderr, /Invalid RAISE_PUBLIC_PORT/, JSON.stringify(port));
    assert.equal(result.configCreated, false, JSON.stringify(port));
  }
});
