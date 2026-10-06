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

function runInstallerWithStubbedRuntime(host, { configDir } = {}) {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "raise-installer-san-"));
  const home = path.join(root, "home");
  const bin = path.join(root, "bin");
  const opensslLog = path.join(root, "openssl.log");
  fs.mkdirSync(home);
  fs.mkdirSync(bin);

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
  writeExecutable(path.join(bin, "node"), "#!/usr/bin/env bash\nexit 0\n");

  try {
    const result = spawnSync("bash", [installer], {
      encoding: "utf8",
      env: {
        ...process.env,
        HOME: home,
        PATH: bin + path.delimiter + process.env.PATH,
        OPENSSL_LOG: opensslLog,
        RAISE_DEPLOY_REVISION: "a".repeat(40),
        RAISE_PUBLIC_HOST: host,
        RAISE_PUBLIC_PORT: "8787",
        ...(configDir ? { RAISE_CONFIG_DIR: configDir } : {})
      }
    });
    const effectiveConfigDir =
      configDir ?? path.join(home, ".config", "raiseai");
    return {
      status: result.status,
      stderr: result.stderr,
      opensslLog: fs.existsSync(opensslLog)
        ? fs.readFileSync(opensslLog, "utf8")
        : "",
      configDir: effectiveConfigDir,
      envCreated: fs.existsSync(path.join(effectiveConfigDir, "gateway.env")),
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
