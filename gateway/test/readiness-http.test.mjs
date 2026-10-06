import test from "node:test";
import assert from "node:assert/strict";
import {
  evaluateReadinessHttpResponse,
  hasJsonMediaType
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
