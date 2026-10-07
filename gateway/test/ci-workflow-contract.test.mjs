import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(HERE, "../..");
const TEST_WORKFLOW = fs.readFileSync(
  path.join(ROOT, ".github", "workflows", "gateway-test.yml"),
  "utf8",
);
const DEPLOY_WORKFLOW = fs.readFileSync(
  path.join(ROOT, ".github", "workflows", "gateway-deploy.yml"),
  "utf8",
);

function externalActionRefs(text) {
  return [...text.matchAll(/^\s*uses:\s*([^@\s]+)@([^\s#]+)(?:\s+#.*)?$/gm)]
    .map((match) => ({ action: match[1], ref: match[2] }))
    .filter(({ action }) => !action.startsWith("./"));
}

function assertImmutableActions(text, requiredActions) {
  const refs = externalActionRefs(text);
  assert.ok(refs.length >= requiredActions.length, "expected required external actions");
  for (const { action, ref } of refs) {
    assert.match(ref, /^[0-9a-f]{40}$/, `${action} must use a 40-char commit SHA`);
  }
  for (const action of requiredActions) {
    assert.ok(refs.some((entry) => entry.action === action), `missing ${action}`);
  }
}

function assertReadOnlyPermissions(text) {
  assert.match(text, /permissions:\s*\n\s+contents:\s*read\b/);
  assert.doesNotMatch(text, /^\s+[A-Za-z0-9_-]+:\s*write\s*$/m);
}

test("gateway test CI pins external actions and exact PR-head checkout", () => {
  assertImmutableActions(TEST_WORKFLOW, ["actions/checkout", "actions/setup-node"]);
  assertReadOnlyPermissions(TEST_WORKFLOW);
  assert.doesNotMatch(TEST_WORKFLOW, /^\s*pull_request_target\s*:/m);
  assert.match(TEST_WORKFLOW, /persist-credentials:\s*false\b/);

  const exactHead = "\${{ github.event.pull_request.head.sha || github.sha }}";
  assert.ok(
    TEST_WORKFLOW.split(exactHead).length - 1 >= 2,
    "checkout ref and EXPECTED_SHA must both use the exact PR head expression",
  );
  assert.match(
    TEST_WORKFLOW,
    /test\s+"\$\(git rev-parse HEAD\)"\s+=\s+"\$EXPECTED_SHA"/,
  );

  for (const requiredPath of [
    '      - "gateway/**"',
    '      - ".github/workflows/gateway-test.yml"',
    '      - ".github/workflows/gateway-deploy.yml"',
  ]) {
    assert.ok(
      TEST_WORKFLOW.includes(requiredPath),
      `missing pull-request trigger for ${requiredPath.trim()}`,
    );
  }
  assert.match(TEST_WORKFLOW, /cancel-in-progress:\s*true\b/);
  assert.match(TEST_WORKFLOW, /timeout-minutes:\s*15\b/);
});

test("gateway deploy CI is pinned, bounded and cannot run on pull requests", () => {
  assertImmutableActions(DEPLOY_WORKFLOW, [
    "actions/checkout",
    "actions/upload-artifact",
  ]);
  assertReadOnlyPermissions(DEPLOY_WORKFLOW);
  assert.match(DEPLOY_WORKFLOW, /persist-credentials:\s*false\b/);
  assert.doesNotMatch(
    DEPLOY_WORKFLOW,
    /^\s*pull_request(?:_target)?\s*:/m,
    "production self-hosted deploy must never be pull-request triggered",
  );
  assert.match(DEPLOY_WORKFLOW, /workflow_dispatch:\s*\{\}/);
  assert.match(
    DEPLOY_WORKFLOW,
    /runs-on:\s*\[self-hosted,\s*vps-bb300bba\]/,
  );
  assert.match(DEPLOY_WORKFLOW, /timeout-minutes:\s*30\b/);
  assert.match(DEPLOY_WORKFLOW, /cancel-in-progress:\s*false\b/);

  const deploySha = "\${{ github.sha }}";
  assert.ok(
    DEPLOY_WORKFLOW.split(deploySha).length - 1 >= 4,
    "checkout, verification and deploy/smoke evidence must stay bound to github.sha",
  );
  assert.match(
    DEPLOY_WORKFLOW,
    /test\s+"\$\(git rev-parse HEAD\)"\s+=\s+"\$EXPECTED_SHA"/,
  );

  for (const requiredPath of [
    '      - "gateway/**"',
    '      - ".github/workflows/gateway-deploy.yml"',
  ]) {
    assert.ok(
      DEPLOY_WORKFLOW.includes(requiredPath),
      `missing deploy trigger for ${requiredPath.trim()}`,
    );
  }
});
