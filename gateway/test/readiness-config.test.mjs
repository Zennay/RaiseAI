import test from "node:test";
import assert from "node:assert/strict";
import { positiveInteger } from "../deploy/readiness-config.mjs";

test("readiness integer config accepts only complete positive integer values", () => {
  assert.equal(positiveInteger("1", 500), 1);
  assert.equal(positiveInteger("0500", 1), 500);
  assert.equal(positiveInteger(250, 1), 250);
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
    String(Number.MAX_SAFE_INTEGER + 1)
  ]) {
    assert.equal(positiveInteger(value, 500), 500, String(value));
  }
});

test("readiness integer config requires a valid positive fallback", () => {
  for (const fallback of [0, -1, 1.5, Number.NaN, Number.POSITIVE_INFINITY]) {
    assert.throws(
      () => positiveInteger("10", fallback),
      /fallback must be a positive safe integer/
    );
  }
});
