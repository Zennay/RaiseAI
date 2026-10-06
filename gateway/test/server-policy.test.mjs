import test from "node:test";
import assert from "node:assert/strict";
import { parseDeployRevision, parseServerPort, validateServerConfig } from "../src/server-policy.mjs";

function valid(overrides = {}) {
  return {
    host: "127.0.0.1",
    port: 8787,
    tlsCert: "",
    tlsKey: "",
    ...overrides
  };
}

test("plaintext listener is allowed only on loopback hosts", () => {
  for (const host of ["127.0.0.1", "127.0.0.2", "localhost", "::1"]) {
    assert.doesNotThrow(() => validateServerConfig(valid({ host })));
  }

  for (const host of ["0.0.0.0", "192.168.1.10", "10.0.0.5", "::"]) {
    assert.throws(
      () => validateServerConfig(valid({ host })),
      /TLS is required/
    );
  }
});

test("non-loopback listener is allowed when certificate and key are both configured", () => {
  assert.doesNotThrow(() =>
    validateServerConfig(valid({
      host: "0.0.0.0",
      tlsCert: "/tmp/cert.pem",
      tlsKey: "/tmp/key.pem"
    }))
  );
});

test("listener host must be a canonical IP address or hostname", () => {
  for (const host of [
    "raise.example.com",
    "gateway-1.internal",
    "127.0.0.1",
    "2001:db8::1"
  ]) {
    assert.doesNotThrow(() =>
      validateServerConfig(valid({
        host,
        tlsCert: host === "127.0.0.1" ? "" : "/tmp/cert.pem",
        tlsKey: host === "127.0.0.1" ? "" : "/tmp/key.pem"
      }))
    );
  }

  for (const host of [
    "http://127.0.0.1",
    "raise ai.local",
    "raise_ai.local",
    "-gateway.local",
    "gateway-.local",
    "gateway..local",
    "[::1]",
    "a".repeat(64) + ".example.com",
    "a".repeat(254)
  ]) {
    assert.throws(
      () => validateServerConfig(valid({
        host,
        tlsCert: "/tmp/cert.pem",
        tlsKey: "/tmp/key.pem"
      })),
      /RAISE_HOST must be an IP address or canonical hostname/,
      host
    );
  }
});

test("TLS configuration fails closed when only one side is configured", () => {
  assert.throws(
    () => validateServerConfig(valid({ tlsCert: "/tmp/cert.pem" })),
    /must be set together/
  );
  assert.throws(
    () => validateServerConfig(valid({ tlsKey: "/tmp/key.pem" })),
    /must be set together/
  );
});

test("listener rejects empty host and invalid ports before binding", () => {
  for (const host of ["", "   "]) {
    assert.throws(
      () => validateServerConfig(valid({ host })),
      /non-empty host/
    );
  }

  for (const port of [0, -1, 65536, 8787.5, Number.NaN]) {
    assert.throws(
      () => validateServerConfig(valid({ port })),
      /integer from 1 through 65535/
    );
  }
});

test("deploy revision accepts only unknown or canonical Git object IDs", () => {
  const sha1 = "0123456789abcdef".repeat(2) + "01234567";
  const sha256 = "0123456789abcdef".repeat(4);

  assert.equal(parseDeployRevision(undefined), "unknown");
  assert.equal(parseDeployRevision("unknown"), "unknown");
  assert.equal(parseDeployRevision(sha1), sha1);
  assert.equal(parseDeployRevision(sha256), sha256);

  for (const value of [
    "",
    " UNKNOWN",
    "unknown ",
    "Unknown",
    "g".repeat(40),
    "A".repeat(40),
    "a".repeat(39),
    "a".repeat(41),
    "a".repeat(63),
    "a".repeat(65),
    "main",
    "v1.2.3",
    "deadbeef\n" + "a".repeat(31)
  ]) {
    assert.throws(
      () => parseDeployRevision(value),
      /canonical 40\/64-character lowercase Git revision/,
      value
    );
  }
});

test("RAISE_PORT parser accepts only canonical decimal environment values", () => {
  assert.equal(parseServerPort(undefined), 8787);
  assert.equal(parseServerPort("1"), 1);
  assert.equal(parseServerPort("8787"), 8787);
  assert.equal(parseServerPort("65535"), 65535);

  for (const value of [
    "",
    "0",
    "00080",
    " 8787",
    "8787 ",
    "+8787",
    "-1",
    "1e3",
    "0x1f90",
    "8787.0",
    "65536"
  ]) {
    assert.throws(
      () => parseServerPort(value),
      /canonical decimal integer from 1 through 65535/,
      value
    );
  }
});

test("listener rejects surrounding whitespace in host and TLS path config", () => {
  for (const host of [" 127.0.0.1", "127.0.0.1 ", "\tlocalhost"]) {
    assert.throws(
      () => validateServerConfig(valid({ host })),
      /RAISE_HOST must not contain surrounding whitespace/
    );
  }

  for (const tlsCert of [" /tmp/cert.pem", "/tmp/cert.pem ", "   "]) {
    assert.throws(
      () => validateServerConfig(valid({
        tlsCert,
        tlsKey: "/tmp/key.pem"
      })),
      /RAISE_TLS_CERT and RAISE_TLS_KEY must not contain surrounding whitespace/
    );
  }

  for (const tlsKey of [" /tmp/key.pem", "/tmp/key.pem ", "\t"]) {
    assert.throws(
      () => validateServerConfig(valid({
        tlsCert: "/tmp/cert.pem",
        tlsKey
      })),
      /RAISE_TLS_CERT and RAISE_TLS_KEY must not contain surrounding whitespace/
    );
  }
});


test("TLS paths must be absolute and free of control characters", () => {
  for (const [tlsCert, tlsKey] of [
    ["cert.pem", "key.pem"],
    ["./cert.pem", "./key.pem"],
    ["/tmp/cert.pem", "key.pem"],
    ["cert.pem", "/tmp/key.pem"],
    ["/tmp/cert\n.pem", "/tmp/key.pem"],
    ["/tmp/cert.pem", "/tmp/key\t.pem"],
    ["/tmp/cert\u0000.pem", "/tmp/key.pem"]
  ]) {
    assert.throws(
      () => validateServerConfig(valid({ tlsCert, tlsKey })),
      /must be absolute paths without control characters/,
      JSON.stringify({ tlsCert, tlsKey })
    );
  }

  assert.doesNotThrow(() =>
    validateServerConfig(valid({
      host: "0.0.0.0",
      tlsCert: "/tmp/raise ai/cert.pem",
      tlsKey: "/tmp/raise ai/key.pem"
    }))
  );
});
