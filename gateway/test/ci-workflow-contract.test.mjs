import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(HERE, "../..");
const WORKFLOW = path.join(ROOT, ".github", "workflows", "gateway-test.yml");
const source = fs.readFileSync(WORKFLOW, "utf8");

function externalActionRefs(text) {
  return [...text.matchAll(/^\s*uses:\s*([^@\s]+)@([^\s#]+)(?:\s+#.*)?$/gm)]
    .map((match) => ({ action: match[1], ref: match[2] }))
    .filter(({ action }) => !action.startsWith("./"));
}

test("gateway CI pins every external action to an immutable commit", () => {
  const refs = externalActionRefs(source);
  assert.ok(refs.length >= 2, "expected checkout and setup-node actions");
  for (const { action, ref } of refs) {
    assert.match(ref, /^[0-9a-f]{40}$/, `${action} must use a 40-char commit SHA`);
  }
  assert.ok(refs.some(({ action }) => action === "actions/checkout"));
  assert.ok(refs.some(({ action }) => action === "actions/setup-node"));
  assert.doesNotMatch(source, /uses:\s+actions\/(?:checkout|setup-node)@v\d+/);
});

test("gateway CI uses a read-only exact-head checkout", () => {
  assert.match(source, /permissions:\s*\n\s+contents:\s*read\b/);
  assert.doesNotMatch(source, /^\s+[A-Za-z0-9_-]+:\s*write\s*$/m);
  assert.doesNotMatch(source, /^\s*pull_request_target\s*:/m);
  assert.match(source, /persist-credentials:\s*false\b/);

  const exactHead = "\${{ github.event.pull_request.head.sha || github.sha }}";
  assert.ok(
    source.split(exactHead).length - 1 >= 2,
    "checkout ref and EXPECTED_SHA must both use the exact PR head expression",
  );
  assert.match(
    source,
    /test\s+"\$\(git rev-parse HEAD\)"\s+=\s+"\$EXPECTED_SHA"/,
  );
});

test("gateway CI reruns when its tested surface or workflow contracts change", () => {
  for (const requiredPath of [
    '      - "gateway/**"',
    '      - ".github/workflows/gateway-test.yml"',
    '      - ".github/workflows/gateway-deploy.yml"',
  ]) {
    assert.ok(
      source.includes(requiredPath),
      `missing pull-request trigger for ${requiredPath.trim()}`,
    );
  }
  assert.match(source, /cancel-in-progress:\s*true\b/);
  assert.match(source, /timeout-minutes:\s*15\b/);
});
