import test from "node:test";
import assert from "node:assert/strict";
import { Readable } from "node:stream";
import {
  MAX_SMOKE_BODY_BYTES,
  readSmokeResponseBody
} from "../deploy/smoke-http.mjs";

function bodyStream(chunks, headers = {}) {
  const stream = Readable.from(chunks);
  stream.headers = headers;
  return stream;
}

test("live smoke body reader accepts bounded exact-length JSON", async () => {
  const body = Buffer.from('{"ok":true}', "utf8");
  const stream = bodyStream([body], {
    "content-length": String(body.length)
  });

  const result = await readSmokeResponseBody(stream);

  assert.equal(result.bodyError, null);
  assert.deepEqual(result.json, { ok: true });
});

test("live smoke body reader rejects oversized declared bodies before reading", async () => {
  const stream = bodyStream([], {
    "content-length": String(MAX_SMOKE_BODY_BYTES + 1)
  });

  const result = await readSmokeResponseBody(stream);

  assert.equal(result.bodyError, "smoke_body_too_large");
  assert.equal(result.json, null);
  assert.equal(stream.destroyed, true);
});

test("live smoke body reader enforces the streamed byte budget", async () => {
  const stream = bodyStream([
    Buffer.alloc(4, 0x61),
    Buffer.alloc(2, 0x62)
  ]);

  const result = await readSmokeResponseBody(stream, { maxBytes: 5 });

  assert.equal(result.bodyError, "smoke_body_too_large");
  assert.equal(result.json, null);
  assert.equal(stream.destroyed, true);
});

test("live smoke body reader rejects malformed and mismatched content lengths", async () => {
  const malformed = bodyStream([Buffer.from("{}")], {
    "content-length": "2x"
  });
  const malformedResult = await readSmokeResponseBody(malformed);
  assert.equal(malformedResult.bodyError, "smoke_content_length_invalid");
  assert.equal(malformed.destroyed, true);

  const mismatched = bodyStream([Buffer.from("{}")], {
    "content-length": "3"
  });
  const mismatchResult = await readSmokeResponseBody(mismatched);
  assert.equal(mismatchResult.bodyError, "smoke_content_length_mismatch");
  assert.equal(mismatchResult.json, null);
});

test("live smoke body reader rejects invalid UTF-8 JSON", async () => {
  const stream = bodyStream([Buffer.from([0xff])]);

  const result = await readSmokeResponseBody(stream);

  assert.equal(result.bodyError, "smoke_body_invalid_json");
  assert.equal(result.json, null);
});

test("live smoke body reader can bound non-JSON responses without parsing them", async () => {
  const body = Buffer.from("not-json", "utf8");
  const stream = bodyStream([body], {
    "content-length": String(body.length)
  });

  const result = await readSmokeResponseBody(stream, { parseJson: false });

  assert.equal(result.bodyError, null);
  assert.equal(result.json, null);
});

test("live smoke body reader destroys broken streams and reports a stable error", async () => {
  let destroyCalls = 0;
  const stream = {
    headers: {},
    destroy() {
      destroyCalls += 1;
    },
    async *[Symbol.asyncIterator]() {
      yield Buffer.from("{");
      throw new Error("broken_stream");
    }
  };

  const result = await readSmokeResponseBody(stream);

  assert.equal(result.bodyError, "smoke_body_read_failed");
  assert.equal(result.json, null);
  assert.equal(destroyCalls, 1);
});

test("live smoke body reader validates its configured byte budget", async () => {
  const stream = bodyStream([Buffer.from("{}")]);

  for (const maxBytes of [0, -1, 1.5, Number.NaN, Number.MAX_SAFE_INTEGER + 1]) {
    await assert.rejects(
      readSmokeResponseBody(stream, { maxBytes }),
      /smoke maxBytes must be a positive safe integer/
    );
  }
});
