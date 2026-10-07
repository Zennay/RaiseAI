import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";

const testDir = path.dirname(fileURLToPath(import.meta.url));
const sourceScript = path.resolve(
  testDir,
  "../deploy/assert-idempotent-redeploy.sh"
);

function writeExecutable(file, content) {
  fs.writeFileSync(file, content, { mode: 0o755 });
}

function runIdempotencyCheck({
  beforeRevision,
  afterRevision,
  expectedRevision,
  extraEnvLines = []
}) {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "raise-idempotency-revision-"));
  const deployDir = path.join(root, "deploy");
  const configDir = path.join(root, "config");
  const tlsDir = path.join(configDir, "tls");
  const binDir = path.join(root, "bin");
  const installerMarker = path.join(root, "installer-called");

  fs.mkdirSync(deployDir);
  fs.mkdirSync(tlsDir, { recursive: true });
  fs.mkdirSync(binDir);
  fs.copyFileSync(
    sourceScript,
    path.join(deployDir, "assert-idempotent-redeploy.sh")
  );

  fs.writeFileSync(
    path.join(configDir, "gateway.env"),
    [
      "RAISE_GATEWAY_TOKEN=" + "t".repeat(40),
      "RAISE_DEPLOY_REVISION=" + beforeRevision,
      ...extraEnvLines,
      ""
    ].join("\n"),
    "utf8"
  );
  fs.writeFileSync(path.join(tlsDir, "gateway-cert.pem"), "fake-cert\n", "utf8");

  writeExecutable(
    path.join(binDir, "openssl"),
    `#!/usr/bin/env bash
set -euo pipefail
case "\${1:-}" in
  x509)
    printf '%s\\n' 'fake-public-key'
    ;;
  pkey)
    cat
    ;;
  dgst)
    cat >/dev/null
    printf '%s\\n' 'SHA2-256(stdin)= ${"b".repeat(64)}'
    ;;
  *)
    exit 2
    ;;
esac
`
  );

  writeExecutable(
    path.join(deployDir, "install-user-gateway.sh"),
    `#!/usr/bin/env bash
set -euo pipefail
: "\${RAISE_CONFIG_DIR:?}"
printf 'called\\n' > "\${FAKE_INSTALLER_MARKER:?}"
env_file="$RAISE_CONFIG_DIR/gateway.env"
revision="\${FAKE_AFTER_REVISION:-\${RAISE_DEPLOY_REVISION:-unknown}}"
tmp="$env_file.tmp"
awk -F= -v revision="$revision" '
  $1 == "RAISE_DEPLOY_REVISION" {
    print "RAISE_DEPLOY_REVISION=" revision
    seen = 1
    next
  }
  { print }
  END {
    if (!seen) {
      print "RAISE_DEPLOY_REVISION=" revision
    }
  }
' "$env_file" > "$tmp"
mv "$tmp" "$env_file"
`
  );

  try {
    const env = {
      ...process.env,
      PATH: binDir + path.delimiter + process.env.PATH,
      RAISE_CONFIG_DIR: configDir,
      FAKE_INSTALLER_MARKER: installerMarker,
      FAKE_AFTER_REVISION: afterRevision
    };
    delete env.RAISE_DEPLOY_REVISION;
    if (expectedRevision !== undefined) {
      env.RAISE_DEPLOY_REVISION = expectedRevision;
    }

    const result = spawnSync(
      "/bin/bash",
      [path.join(deployDir, "assert-idempotent-redeploy.sh")],
      {
        encoding: "utf8",
        env
      }
    );

    return {
      status: result.status,
      stdout: result.stdout,
      stderr: result.stderr,
      installerCalled: fs.existsSync(installerMarker)
    };
  } finally {
    fs.rmSync(root, { recursive: true, force: true });
  }
}

test("idempotency proof rejects revision drift even without an expected revision env", () => {
  const before = "a".repeat(40);
  const result = runIdempotencyCheck({
    beforeRevision: before,
    afterRevision: "unknown"
  });

  assert.notEqual(result.status, 0, result.stdout + result.stderr);
  assert.equal(result.installerCalled, true);
  assert.match(result.stderr, /Idempotency failure: deploy revision changed/);
});

test("idempotency proof accepts a redeploy that preserves the recorded revision", () => {
  const revision = "c".repeat(40);
  const result = runIdempotencyCheck({
    beforeRevision: revision,
    afterRevision: revision
  });

  assert.equal(result.status, 0, result.stdout + result.stderr);
  assert.equal(result.installerCalled, true);
  assert.match(
    result.stdout,
    /Idempotent redeploy verified: token, TLS public key and deploy revision preserved/
  );
});

test("expected revision mismatch fails before the redeploy side effect", () => {
  const result = runIdempotencyCheck({
    beforeRevision: "d".repeat(40),
    afterRevision: "d".repeat(40),
    expectedRevision: "e".repeat(40)
  });

  assert.notEqual(result.status, 0, result.stdout + result.stderr);
  assert.equal(result.installerCalled, false);
  assert.match(
    result.stderr,
    /pre-redeploy revision does not match expected revision/
  );
});

test("ambiguous pre-redeploy revision is rejected before installer execution", () => {
  const revision = "f".repeat(40);
  const result = runIdempotencyCheck({
    beforeRevision: revision,
    afterRevision: revision,
    extraEnvLines: ["RAISE_DEPLOY_REVISION=shadow"]
  });

  assert.notEqual(result.status, 0, result.stdout + result.stderr);
  assert.equal(result.installerCalled, false);
  assert.match(
    result.stderr,
    /Expected exactly one RAISE_DEPLOY_REVISION in gateway env/
  );
});
