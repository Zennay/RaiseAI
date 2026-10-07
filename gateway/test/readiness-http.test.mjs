import test from "node:test";
import assert from "node:assert/strict";
import { Readable } from "node:stream";
import {
  armReadinessRequestDeadline,
  evaluateReadinessHttpResponse,
  hasJsonMediaType,
  MAX_READINESS_BODY_BYTES,
  MAX_READINESS_REQUEST_MS,
  readinessRequestBudget,
  readReadinessJson
} from "../deploy/readiness-http.mjs";

const REVISION = "a".repeat(40);

test("readiness attempt budget never exceeds the remaining global gate", () => {
  assert.equal(readinessRequestBudget(1), 1);
  assert.equal(readinessRequestBudget(4999), 4999);
  assert.equal(readinessRequestBudget(5000), 5000);
  assert.equal(readinessRequestBudget(5001), 5000);
  assert.equal(readinessRequestBudget(30_000), MAX_READINESS_REQUEST_MS);

  for (const remainingMs of [
    0,
    -1,
    1.5,
    Number.NaN,
    Number.MAX_SAFE_INTEGER + 1
  ]) {
    assert.throws(
      () => readinessRequestBudget(remainingMs),
      /remaining budget must be a positive safe integer/
    );
  }
});

test("readiness absolute deadline destroys a request at the hard budget", () => {
  let scheduled = null;
  let destroyedWith = null;
  const request = {
    destroy(error) {
      destroyedWith = error;
    }
  };

  armReadinessRequestDeadline(request, {
    setTimeoutImpl(callback, timeoutMs) {
      scheduled = { callback, timeoutMs };
      return "readiness-deadline";
    },
    clearTimeoutImpl() {
      throw new Error("must not clear before deadline fires");
    }
  });

  assert.equal(scheduled.timeoutMs, MAX_READINESS_REQUEST_MS);
  scheduled.callback();
  assert.equal(
    destroyedWith?.message,
    "readiness_request_deadline_exceeded"
  );
});

test("settled readiness requests cancel their absolute deadline once", () => {
  let scheduled = null;
  const cleared = [];
  let destroyCalls = 0;
  const request = {
    destroy() {
      destroyCalls += 1;
    }
  };

  const cancel = armReadinessRequestDeadline(request, {
    timeoutMs: 321,
    setTimeoutImpl(callback, timeoutMs) {
      scheduled = { callback, timeoutMs };
      return "readiness-deadline";
    },
    clearTimeoutImpl(handle) {
      cleared.push(handle);
    }
  });

  assert.equal(scheduled.timeoutMs, 321);
  cancel();
  cancel();
  scheduled.callback();

  assert.deepEqual(cleared, ["readiness-deadline"]);
  assert.equal(destroyCalls, 0);
});

test("readiness absolute deadline validates request and timer inputs", () => {
  assert.throws(
    () => armReadinessRequestDeadline(null),
    /readiness request must expose destroy/
  );
  assert.throws(
    () => armReadinessRequestDeadline({ destroy: true }),
    /readiness request must expose destroy/
  );

  const request = { destroy() {} };
  for (const timeoutMs of [0, -1, 1.5, Number.NaN, Number.MAX_SAFE_INTEGER + 1]) {
    assert.throws(
      () => armReadinessRequestDeadline(request, { timeoutMs }),
      /readiness request timeout must be a positive safe integer/
    );
  }

  assert.throws(
    () => armReadinessRequestDeadline(request, { setTimeoutImpl: null }),
    /timer functions must be callable/
  );
  assert.throws(
    () => armReadinessRequestDeadline(request, { clearTimeoutImpl: null }),
    /timer functions must be callable/
  );
});

test("readiness deadline cancellation is best-effort after settlement", () => {
  const request = { destroy() {} };
  const cancel = armReadinessRequestDeadline(request, {
    setTimeoutImpl() {
      return "readiness-deadline";
    },
    clearTimeoutImpl() {
      throw new Error("cleanup_failed");
    }
  });

  assert.doesNotThrow(cancel);
  assert.doesNotThrow(cancel);
});

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

test("readiness body reader validates declared Content-Length before trust", async () => {
  const exactBody = Buffer.from('{"ok":true}');
  const exact = Readable.from([exactBody]);
  exact.headers = { "content-length": String(exactBody.length) };
  assert.deepEqual(await readReadinessJson(exact), {
    json: { ok: true },
    bodyError: null
  });

  let readStarted = false;
  const oversized = {
    headers: { "content-length": String(MAX_READINESS_BODY_BYTES + 1) },
    async *[Symbol.asyncIterator]() {
      readStarted = true;
      yield Buffer.from("{}");
    }
  };
  assert.deepEqual(await readReadinessJson(oversized), {
    json: null,
    bodyError: "health_body_too_large"
  });
  assert.equal(readStarted, false);

  for (const declared of ["", " ", "abc", "-1", "1.5", "10, 10"]) {
    const malformed = Readable.from([Buffer.from("{}")]);
    malformed.headers = { "content-length": declared };
    assert.deepEqual(await readReadinessJson(malformed), {
      json: null,
      bodyError: "health_content_length_invalid"
    }, JSON.stringify(declared));
  }

  for (const declared of [exactBody.length - 1, exactBody.length + 1]) {
    const mismatched = Readable.from([exactBody]);
    mismatched.headers = { "content-length": String(declared) };
    assert.deepEqual(await readReadinessJson(mismatched), {
      json: null,
      bodyError: "health_content_length_mismatch"
    }, String(declared));
  }
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
