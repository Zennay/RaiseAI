import test from "node:test";
import assert from "node:assert/strict";
import { Readable } from "node:stream";
import {
  evaluateReadinessHttpResponse,
  hasJsonMediaType,
  MAX_READINESS_BODY_BYTES,
  readReadinessJson
} from "../deploy/readiness-http.mjs";

const REVISION = "a".repeat(40);

test("readiness HTTP gate accepts only application/json media identity", () => {
  for (const value of [
    "application/json",
    "application/json; charset=utf-8",
    "Application/JSON; Charset=UTF-8",
    'application/json; charset="UTF-8"'
  ]) {
    assert.equal(hasJsonMediaType(value), true, value);
  }

  for (const value of [
    undefined,
    null,
    "",
    "text/plain",
    "text/html; charset=utf-8",
    "application/problem+json",
    "application/json;",
    "application/json; charset=iso-8859-1",
    "application/json; charset=",
    "application/json; profile=watch",
    "application/json; charset=utf-8; profile=watch",
    "application/json; charset=utf-8; charset=utf-8"
  ]) {
    assert.equal(hasJsonMediaType(value), false, String(value));
  }
});

test("readiness body reader enforces byte bounds and strict UTF-8", async () => {
  const prefix = '{"pad":"';
  const suffix = '"}';
  const padLength =
    MAX_READINESS_BODY_BYTES -
    Buffer.byteLength(prefix) -
    Buffer.byteLength(suffix);
  const boundaryBody = prefix + "x".repeat(padLength) + suffix;
  assert.equal(Buffer.byteLength(boundaryBody), MAX_READINESS_BODY_BYTES);

  const boundary = await readReadinessJson(
    Readable.from([Buffer.from(boundaryBody)])
  );
  assert.equal(boundary.bodyError, null);
  assert.equal(boundary.json.pad.length, padLength);

  const oversized = await readReadinessJson(
    Readable.from([
      Buffer.alloc(MAX_READINESS_BODY_BYTES, 0x20),
      Buffer.from("x")
    ])
  );
  assert.deepEqual(oversized, {
    json: null,
    bodyError: "health_body_too_large"
  });

  for (const payload of [
    Buffer.from('{"ok":'),
    Buffer.from([0xff])
  ]) {
    const invalid = await readReadinessJson(Readable.from([payload]));
    assert.deepEqual(invalid, {
      json: null,
      bodyError: "health_body_invalid_json"
    });
  }

  await assert.rejects(
    readReadinessJson(Readable.from([Buffer.from("{}")]), { maxBytes: 0 }),
    /positive safe integer/
  );
});

test("readiness HTTP gate preserves bounded-body failure reasons", () => {
  const result = evaluateReadinessHttpResponse({
    status: 200,
    contentType: "application/json; charset=utf-8",
    json: null,
    bodyError: "health_body_too_large",
    expectedRevision: REVISION
  });

  assert.deepEqual(result, {
    ok: false,
    reason: "health_body_too_large",
    revision: null
  });
});

test("readiness HTTP gate refuses JSON-looking bodies with the wrong media type", () => {
  const result = evaluateReadinessHttpResponse({
    status: 200,
    contentType: "text/plain",
    json: {
      ok: true,
      service: "raise-gateway",
      revision: REVISION
    },
    expectedRevision: REVISION
  });

  assert.deepEqual(result, {
    ok: false,
    reason: "health_media_type_invalid",
    revision: null
  });
});

test("readiness HTTP gate delegates valid JSON responses to revision policy", () => {
  const result = evaluateReadinessHttpResponse({
    status: 200,
    contentType: "application/json; charset=utf-8",
    json: {
      ok: true,
      service: "raise-gateway",
      revision: REVISION
    },
    expectedRevision: REVISION
  });

  assert.equal(result.ok, true);
  assert.equal(result.reason, "ready");
  assert.equal(result.revision, REVISION);
});
