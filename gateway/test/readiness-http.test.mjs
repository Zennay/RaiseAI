import assert from "node:assert/strict";
import test from "node:test";
import { Readable } from "node:stream";
import {
  isReadinessJsonContentType,
  readReadinessJson
} from "../deploy/readiness-http.mjs";

function response(chunks, contentType = "application/json; charset=utf-8") {
  const stream = Readable.from(chunks);
  stream.headers = { "content-type": contentType };
  return stream;
}

test("readiness JSON media type accepts only JSON with optional UTF-8 charset", () => {
  for (const value of [
    "application/json",
    "application/json; charset=utf-8",
    "Application/JSON; Charset=UTF-8",
    'application/json; charset="utf-8"'
  ]) {
    assert.equal(isReadinessJsonContentType(value), true, value);
  }

  for (const value of [
    undefined,
    "",
    "text/plain",
    "application/problem+json",
    "application/json; charset=iso-8859-1",
    "application/json; profile=health",
    "application/json; charset=utf-8; profile=health"
  ]) {
    assert.equal(isReadinessJsonContentType(value), false, String(value));
  }
});

test("readiness body parser accepts bounded UTF-8 JSON", async () => {
  const parsed = await readReadinessJson(
    response([Buffer.from('{"ok":true,"revision":"abc"}')])
  );

  assert.deepEqual(parsed, { ok: true, revision: "abc" });
});

test("readiness body parser rejects non-JSON media before consuming evidence", async () => {
  const res = response(
    [Buffer.from('{"ok":true}')],
    "text/plain; charset=utf-8"
  );

  await assert.rejects(
    readReadinessJson(res),
    /health_response_not_json/
  );
});

test("readiness body parser rejects oversized responses", async () => {
  await assert.rejects(
    readReadinessJson(
      response([Buffer.alloc(9), Buffer.alloc(8)]),
      { maxBodyBytes: 16 }
    ),
    /health_response_too_large/
  );
});

test("readiness body parser rejects invalid UTF-8", async () => {
  await assert.rejects(
    readReadinessJson(response([Buffer.from([0xc3, 0x28])])),
    /health_response_invalid_utf8/
  );
});

test("readiness body parser rejects malformed JSON", async () => {
  await assert.rejects(
    readReadinessJson(response([Buffer.from("{not-json")])),
    /health_response_invalid_json/
  );
});
