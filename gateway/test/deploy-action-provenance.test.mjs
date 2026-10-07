import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(HERE, "../..");
const DEPLOY = fs.readFileSync(
  path.join(ROOT, ".github", "workflows", "gateway-deploy.yml"),
  "utf8",
);

const CHECKOUT_SHA = "3d3c42e5aac5ba805825da76410c181273ba90b1";
const UPLOAD_ARTIFACT_SHA = "043fb46d1a93c77aae656e7c1c64a875d1fc6a0a";

test("gateway deploy external action releases stay audited Node 24 pins", () => {
  const refs = [...DEPLOY.matchAll(
    /^\s*(?:-\s*)?uses:\s*([^@\s]+)@([^\s#]+)(?:\s+#.*)?$/gm,
  )].map((match) => [match[1], match[2]]);

  assert.deepEqual(refs, [
    ["actions/checkout", CHECKOUT_SHA],
    ["actions/upload-artifact", UPLOAD_ARTIFACT_SHA],
  ]);
  assert.ok(
    DEPLOY.includes(
      `uses: actions/checkout@${CHECKOUT_SHA} # v7.0.1 (node24)`,
    ),
  );
  assert.ok(
    DEPLOY.includes(
      `uses: actions/upload-artifact@${UPLOAD_ARTIFACT_SHA} # v7.0.1 (node24)`,
    ),
  );
  assert.match(DEPLOY, /persist-credentials:\s*false\b/);
});
