import assert from "node:assert/strict";
import test from "node:test";
import { evaluateReadinessResponse } from "../deploy/readiness-policy.mjs";

const revision = "166e62cc646a75d50485090cb4a117bc5e070ffc";

test("readiness passes only for healthy exact revision", () => {
  assert.deepEqual(
    evaluateReadinessResponse({
      status: 200,
      json: { ok: true, revision },
      expectedRevision: revision
    }),
    { ok: true, reason: "ready", revision }
  );
});

test("readiness rejects stale live revision", () => {
  const result = evaluateReadinessResponse({
    status: 200,
    json: { ok: true, revision: "stale" },
    expectedRevision: revision
  });

  assert.equal(result.ok, false);
  assert.equal(result.reason, "health_revision_mismatch");
  assert.equal(result.revision, "stale");
});

test("readiness rejects unhealthy and malformed health responses", () => {
  assert.equal(
    evaluateReadinessResponse({
      status: 503,
      json: { ok: false },
      expectedRevision: revision
    }).reason,
    "health_http_503"
  );

  assert.equal(
    evaluateReadinessResponse({
      status: 200,
      json: { ok: false, revision },
      expectedRevision: revision
    }).reason,
    "health_not_ok"
  );

  assert.equal(
    evaluateReadinessResponse({
      status: 200,
      json: { ok: true },
      expectedRevision: revision
    }).reason,
    "health_revision_missing"
  );
});
