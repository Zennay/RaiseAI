import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const CHECKOUT_SHA = "3d3c42e5aac5ba805825da76410c181273ba90b1";
const SETUP_NODE_SHA = "820762786026740c76f36085b0efc47a31fe5020";
const HERE = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(HERE, "../..");
const HOSTED = fs.readFileSync(path.join(ROOT, ".github", "workflows", "gateway-test.yml"), "utf8");
const SELF_HOSTED = fs.readFileSync(
  path.join(ROOT, ".github", "workflows", "gateway-quality-selfhosted.yml"),
  "utf8",
);

function stepBlock(text, name) {
  const marker = `      - name: ${name}`;
  const start = text.indexOf(marker);
  assert.notEqual(start, -1, `missing step: ${name}`);
  const next = text.indexOf("\n      - name:", start + marker.length);
  return text.slice(start, next === -1 ? undefined : next);
}

test("hosted gateway tests bypass mutable package scripts", () => {
  assert.equal(HOSTED.split("          node --test").length - 1, 1);
  assert.equal(HOSTED.includes("          npm test"), false);
  assert.equal(HOSTED.includes("          npm run test"), false);
});

test("self-hosted gateway quality gate is exact-head and VPS-bound", () => {
  assert.ok(SELF_HOSTED.includes("    runs-on: [self-hosted, vps-bb300bba]"));
  assert.ok(SELF_HOSTED.includes("    timeout-minutes: 10"));
  assert.ok(SELF_HOSTED.includes("permissions:\n  contents: read"));
  assert.equal(/^\s+[A-Za-z0-9_-]+:\s*write\s*$/m.test(SELF_HOSTED), false);
  assert.equal(/^\s*pull_request_target\s*:/m.test(SELF_HOSTED), false);
  assert.equal(SELF_HOSTED.includes("${{ secrets."), false);

  assert.ok(SELF_HOSTED.includes(`uses: actions/checkout@${CHECKOUT_SHA} # v7.0.1 (node24)`));
  assert.ok(SELF_HOSTED.includes(`uses: actions/setup-node@${SETUP_NODE_SHA} # v7.0.0 (node24)`));
  assert.ok(SELF_HOSTED.includes("          persist-credentials: false"));
  assert.ok(SELF_HOSTED.includes('          node-version: "22"'));
  assert.ok(SELF_HOSTED.includes("          package-manager-cache: false"));

  const exactHead = "${{ github.event.pull_request.head.sha || github.sha }}";
  assert.equal(SELF_HOSTED.split(exactHead).length - 1, 2);
  assert.ok(SELF_HOSTED.includes('          test "$(git rev-parse HEAD)" = "$EXPECTED_SHA"'));
});

test("self-hosted gateway gate runs full tests with strict Bash", () => {
  for (const name of [
    "Verify exact tested revision",
    "Verify Node runtime",
    "Run gateway regressions directly",
    "Verify worktree remains clean",
  ]) {
    const block = stepBlock(SELF_HOSTED, name);
    assert.ok(block.includes("        shell: bash"));
    assert.ok(block.includes("          set -euo pipefail"));
  }
  assert.equal(SELF_HOSTED.split("          node --test").length - 1, 1);
  assert.equal(SELF_HOSTED.includes("          npm test"), false);
  assert.equal(SELF_HOSTED.includes("          npm run test"), false);
  assert.equal(SELF_HOSTED.includes("continue-on-error: true"), false);
});

test("self-hosted gateway gate checks runtime, triggers and clean worktree", () => {
  assert.ok(SELF_HOSTED.includes("process.versions.node.split('.')[0]"));
  for (const requiredPath of [
    '      - "gateway/**"',
    '      - ".github/workflows/gateway-test.yml"',
    '      - ".github/workflows/gateway-quality-selfhosted.yml"',
  ]) {
    assert.ok(SELF_HOSTED.includes(requiredPath), `missing trigger: ${requiredPath.trim()}`);
  }
  assert.ok(SELF_HOSTED.includes("  workflow_dispatch: {}"));
  assert.ok(SELF_HOSTED.includes("  cancel-in-progress: true"));
  for (const command of [
    'git -C "$GITHUB_WORKSPACE" diff --exit-code -- .',
    'git -C "$GITHUB_WORKSPACE" diff --cached --exit-code -- .',
    'test -z "$(git -C "$GITHUB_WORKSPACE" ls-files --others --exclude-standard)"',
  ]) {
    assert.equal(SELF_HOSTED.split(command).length - 1, 1);
  }
});
