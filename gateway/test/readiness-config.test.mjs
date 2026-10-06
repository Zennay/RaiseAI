import test from "node:test";
import assert from "node:assert/strict";
import { httpsOrigin, positiveInteger } from "../deploy/readiness-config.mjs";

test("readiness integer config accepts only complete positive integer values", () => {
  assert.equal(positiveInteger("1", 500), 1);
  assert.equal(positiveInteger("0500", 1), 500);
  assert.equal(positiveInteger(250, 1), 250);
  assert.equal(positiveInteger("2147483647", 1), 2_147_483_647);
});

test("readiness integer config falls back on malformed or unsafe values", () => {
  for (const value of [
    "",
    "0",
    "-1",
    "1.5",
    "500ms",
    "2e3",
    "Infinity",
    "NaN",
    null,
    undefined,
    "2147483648",
    String(Number.MAX_SAFE_INTEGER),
    String(Number.MAX_SAFE_INTEGER + 1)
  ]) {
    assert.equal(positiveInteger(value, 500), 500, String(value));
  }
});

test("readiness integer config requires a valid positive fallback", () => {
  for (const fallback of [
    0,
    -1,
    1.5,
    2_147_483_648,
    Number.NaN,
    Number.POSITIVE_INFINITY
  ]) {
    assert.throws(
      () => positiveInteger("10", fallback),
      /fallback must be a positive timer-safe integer/
    );
  }
});

test("live probe URL accepts only HTTPS origins", () => {
  const plain = httpsOrigin("https://raise.example");
  assert.equal(plain.protocol, "https:");
  assert.equal(plain.hostname, "raise.example");
  assert.equal(plain.port, "");

  const customPort = httpsOrigin("https://raise.example:8787/");
  assert.equal(customPort.hostname, "raise.example");
  assert.equal(customPort.port, "8787");

  for (const value of [
    "",
    "http://raise.example",
    "ftp://raise.example",
    "https://user@raise.example",
    "https://user:pass@raise.example",
    "https://raise.example/health",
    "https://raise.example/?probe=1",
    "https://raise.example/#health",
    " https://raise.example",
    "https://raise.example ",
    "https://raise.example\t"
  ]) {
    assert.throws(
      () => httpsOrigin(value),
      /must be a valid HTTPS origin/,
      value
    );
  }
});
