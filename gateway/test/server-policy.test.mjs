import test from "node:test";
import assert from "node:assert/strict";
import { parseServerPort, validateServerConfig } from "../src/server-policy.mjs";

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
