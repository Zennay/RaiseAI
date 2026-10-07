import assert from "node:assert/strict";
import { execFileSync, spawnSync } from "node:child_process";
import { lstatSync, readFileSync } from "node:fs";
import { dirname, extname, resolve } from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";
import { TextDecoder } from "node:util";

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const WORKFLOW_PATH = resolve(
  ROOT,
  ".github",
  "workflows",
  "javascript-surface-contract.yml",
);
const WORKFLOW = readFileSync(WORKFLOW_PATH, "utf8");
const EXTENSIONS = new Set([".js", ".mjs", ".cjs"]);
const STRICT_UTF8 = new TextDecoder("utf-8", { fatal: true });
const UTF8_BOM = Buffer.from([0xef, 0xbb, 0xbf]);
const EXPECTED_CRITICAL = new Set([
  "app/src/main/assets/raiseai_wear/wear.js",
  "gateway/src/server.mjs",
  "gateway/test/ci-workflow-contract.test.mjs",
  "tests/javascript_surface_contract.test.mjs",
]);

function trackedJavaScriptPaths() {
  return execFileSync("git", ["ls-files", "-z"], {
    cwd: ROOT,
    encoding: "utf8",
  })
    .split("\0")
    .filter(Boolean)
    .filter((path) => EXTENSIONS.has(extname(path)))
    .sort();
}

function decodeCanonicalJavaScriptSource(raw, label) {
  assert.equal(
    raw.subarray(0, UTF8_BOM.length).equals(UTF8_BOM),
    false,
    `${label} must not start with a UTF-8 BOM`,
  );
  const source = STRICT_UTF8.decode(raw);
  assert.equal(source.includes("\0"), false, `${label} must not contain NUL bytes`);
  assert.equal(source.includes("\r"), false, `${label} must use LF-only line endings`);
  return source;
}

function triggerPaths(event) {
  const lines = WORKFLOW.split("\n");
  const eventIndex = lines.indexOf(`  ${event}:`);
  assert.notEqual(eventIndex, -1, `${event} trigger must exist`);

  const body = [];
  for (const line of lines.slice(eventIndex + 1)) {
    if (line && !line.startsWith("    ")) {
      break;
    }
    body.push(line);
  }

  const pathsIndex = body.indexOf("    paths:");
  assert.notEqual(pathsIndex, -1, `${event} must define paths`);

  const paths = [];
  for (const line of body.slice(pathsIndex + 1)) {
    const match = line.match(/^      - "([^"]+)"$/);
    if (!match) {
      break;
    }
    paths.push(match[1]);
  }
  return paths;
}

test("tracked JavaScript surface is nonempty and includes critical files", () => {
  const paths = trackedJavaScriptPaths();
  assert.ok(paths.length > 0, "tracked JavaScript discovery must find files");
  for (const critical of EXPECTED_CRITICAL) {
    assert.ok(paths.includes(critical), `${critical} must remain in dynamic discovery`);
  }
});

test("every tracked JavaScript file is regular, canonical and syntax-valid", () => {
  for (const relative of trackedJavaScriptPaths()) {
    const absolute = resolve(ROOT, relative);
    const stat = lstatSync(absolute);
    assert.equal(
      stat.isSymbolicLink(),
      false,
      `${relative} must not use symlink indirection`,
    );
    assert.equal(stat.isFile(), true, `${relative} must be a regular file`);
    assert.doesNotThrow(
      () => decodeCanonicalJavaScriptSource(readFileSync(absolute), relative),
      `${relative} must be canonical strict UTF-8 JavaScript source`,
    );

    const checked = spawnSync(process.execPath, ["--check", relative], {
      cwd: ROOT,
      encoding: "utf8",
      stdio: "pipe",
    });
    assert.equal(
      checked.status,
      0,
      `${relative} must pass node --check under the audited runtime`,
    );
  }
});

test("strict UTF-8 decoder rejects malformed JavaScript source bytes", () => {
  assert.throws(
    () => STRICT_UTF8.decode(Buffer.from([0x2f, 0x2f, 0x20, 0xff, 0x0a])),
    /encoded data was not valid|invalid/i,
  );
});

test("canonical JavaScript decoder rejects BOM, CR and NUL bytes", () => {
  assert.throws(
    () => decodeCanonicalJavaScriptSource(
      Buffer.concat([UTF8_BOM, Buffer.from("const value = 1;\n")]),
      "fixture.mjs",
    ),
    /UTF-8 BOM/,
  );
  for (const source of ["const value = 1;\r\n", "const value = 1;\r"]) {
    assert.throws(
      () => decodeCanonicalJavaScriptSource(Buffer.from(source), "fixture.mjs"),
      /LF-only line endings/,
    );
  }
  assert.throws(
    () => decodeCanonicalJavaScriptSource(
      Buffer.from("const value = 1;\0\n"),
      "fixture.mjs",
    ),
    /NUL bytes/,
  );
});

test("workflow triggers cover current and future JavaScript surfaces", () => {
  const expected = [
    "*.js",
    "**/*.js",
    "*.mjs",
    "**/*.mjs",
    "*.cjs",
    "**/*.cjs",
    "tests/javascript_surface_contract.test.mjs",
    ".github/workflows/javascript-surface-contract.yml",
  ];
  assert.deepEqual(triggerPaths("push"), expected);
  assert.deepEqual(triggerPaths("pull_request"), expected);
});

test("workflow is hosted, read-only, exact-head, bounded and secret-free", () => {
  assert.match(WORKFLOW, /^name: JavaScript surface contract CI$/m);
  assert.match(WORKFLOW, /runs-on: ubuntu-24\.04/);
  assert.doesNotMatch(WORKFLOW, /self-hosted/);
  assert.match(WORKFLOW, /permissions:\n  contents: read\n/);
  assert.doesNotMatch(WORKFLOW, /\$\{\{\s*secrets\./);
  assert.doesNotMatch(WORKFLOW, /^\s*environment\s*:/m);
  assert.doesNotMatch(WORKFLOW, /^\s+if:\s*/m);
  assert.doesNotMatch(WORKFLOW, /continue-on-error:\s*true/);
  assert.doesNotMatch(WORKFLOW, /pull_request_target:/);
  assert.match(WORKFLOW, /timeout-minutes: 5/);
  assert.match(WORKFLOW, /cancel-in-progress: true/);
  assert.match(WORKFLOW, /persist-credentials: false/);

  const expression =
    "${{ github.event_name == 'pull_request' && github.event.pull_request.head.sha || github.sha }}";
  assert.equal(WORKFLOW.split(expression).length - 1, 2);
});

test("workflow uses only audited immutable external actions", () => {
  const refs = [...WORKFLOW.matchAll(/^\s*(?:-\s*)?uses:\s*([^@\s]+)@([^\s#]+)/gm)]
    .map((match) => [match[1], match[2]]);

  assert.deepEqual(
    refs.map(([action]) => action),
    ["actions/checkout", "actions/setup-node"],
  );
  for (const [, ref] of refs) {
    assert.match(ref, /^[0-9a-f]{40}$/);
  }

  assert.match(
    WORKFLOW,
    /actions\/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1/,
  );
  assert.match(
    WORKFLOW,
    /actions\/setup-node@820762786026740c76f36085b0efc47a31fe5020/,
  );
});

test("workflow pins the audited Node runtime and disables package cache", () => {
  assert.match(WORKFLOW, /node-version: "22\.23\.3"/);
  assert.match(WORKFLOW, /package-manager-cache: false/);
  assert.match(
    WORKFLOW,
    /node -e 'if \(process\.version !== "v22\.23\.3"\) \{ throw new Error\(process\.version\) \}'/,
  );
  assert.match(
    WORKFLOW,
    /node --test tests\/javascript_surface_contract\.test\.mjs/,
  );
});

test("every run step is explicit strict Bash", () => {
  const lines = WORKFLOW.split("\n");
  const runIndices = lines
    .map((line, index) => (line === "        run: |" ? index : -1))
    .filter((index) => index >= 0);
  const stepStarts = lines
    .map((line, index) => (line.startsWith("      - name:") ? index : -1))
    .filter((index) => index >= 0);

  assert.ok(runIndices.length > 0);
  for (const runIndex of runIndices) {
    const stepStart = Math.max(...stepStarts.filter((index) => index < runIndex));
    const later = stepStarts.filter((index) => index > stepStart);
    const stepEnd = later.length ? Math.min(...later) : lines.length;
    const step = lines.slice(stepStart, stepEnd);

    assert.ok(step.includes("        shell: bash"));
    assert.equal(lines[runIndex + 1], "          set -euo pipefail");
  }
});

test("workflow keeps exact top-level and job execution surfaces", () => {
  const lines = WORKFLOW.split("\n");
  const topLevel = lines
    .map((line) => line.match(/^([A-Za-z0-9_-]+):.*$/)?.[1])
    .filter(Boolean);
  assert.deepEqual(topLevel, ["name", "on", "permissions", "concurrency", "jobs"]);

  const jobsBlock = WORKFLOW.split("\njobs:\n", 2)[1];
  assert.ok(jobsBlock);
  const jobKeys = jobsBlock
    .split("\n")
    .slice(1)
    .map((line) => line.match(/^    ([A-Za-z0-9_-]+):.*$/)?.[1])
    .filter(Boolean);
  assert.deepEqual(jobKeys, ["runs-on", "timeout-minutes", "env", "steps"]);
});

test("workflow leaves the checkout clean after validation", () => {
  assert.match(WORKFLOW, /git diff --exit-code -- \./);
  assert.match(WORKFLOW, /git diff --cached --exit-code -- \./);
  assert.match(
    WORKFLOW,
    /test -z "\$\(git ls-files --others --exclude-standard\)"/,
  );
});


test("workflow trigger, concurrency and env surfaces are exact", () => {
  const lines = WORKFLOW.split("\n");
  const onStart = lines.indexOf("on:") + 1;
  const permissionsStart = lines.indexOf("permissions:");
  const events = lines
    .slice(onStart, permissionsStart)
    .map((line) => line.match(/^  ([A-Za-z0-9_-]+):$/)?.[1])
    .filter(Boolean);
  assert.deepEqual(events, ["push", "pull_request"]);

  function eventBlock(event) {
    const start = lines.indexOf(`  ${event}:`) + 1;
    const block = [];
    for (const line of lines.slice(start)) {
      if (line && !line.startsWith("    ")) {
        break;
      }
      block.push(line);
    }
    return block;
  }

  const push = eventBlock("push");
  assert.deepEqual(
    push
      .map((line) => line.match(/^    ([A-Za-z0-9_-]+):$/)?.[1])
      .filter(Boolean),
    ["branches", "paths"],
  );
  assert.equal(push[push.indexOf("    branches:") + 1], "      - main");

  const pullRequest = eventBlock("pull_request");
  assert.deepEqual(
    pullRequest
      .map((line) => line.match(/^    ([A-Za-z0-9_-]+):$/)?.[1])
      .filter(Boolean),
    ["paths"],
    "pull_request must not gain type or branch filters that can skip synchronize validation",
  );

  const concurrencyStart = lines.indexOf("concurrency:") + 1;
  const jobsStart = lines.indexOf("jobs:");
  assert.deepEqual(
    lines
      .slice(concurrencyStart, jobsStart)
      .map((line) => line.match(/^  ([A-Za-z0-9_-]+):.*$/)?.[1])
      .filter(Boolean),
    ["group", "cancel-in-progress"],
  );

  const envStart = lines.indexOf("    env:") + 1;
  const envKeys = [];
  for (const line of lines.slice(envStart)) {
    const match = line.match(/^      ([A-Za-z0-9_-]+):.*$/);
    if (!match) {
      break;
    }
    envKeys.push(match[1]);
  }
  assert.deepEqual(
    envKeys,
    ["LANG", "LC_ALL", "TZ"],
    "JavaScript runtime environment must not gain unreviewed controls",
  );
});

test("workflow step and nested mapping surfaces are exact", () => {
  const lines = WORKFLOW.split("\n");
  const stepStarts = lines
    .map((line, index) => (line.startsWith("      - name:") ? index : -1))
    .filter((index) => index >= 0);
  const expectedNames = [
    "Checkout exact tested revision",
    "Verify exact tested revision",
    "Set up audited Node runtime",
    "Verify Node runtime",
    "Validate tracked JavaScript surface",
    "Verify worktree remains clean",
  ];
  assert.deepEqual(
    stepStarts.map((index) => lines[index].replace("      - name: ", "")),
    expectedNames,
    "JavaScript workflow must not gain unreviewed steps",
  );

  const expectedKeys = new Map([
    ["Checkout exact tested revision", ["name", "uses", "with"]],
    ["Verify exact tested revision", ["name", "shell", "env", "run"]],
    ["Set up audited Node runtime", ["name", "uses", "with"]],
    ["Verify Node runtime", ["name", "shell", "run"]],
    ["Validate tracked JavaScript surface", ["name", "shell", "run"]],
    ["Verify worktree remains clean", ["name", "shell", "run"]],
  ]);

  function stepNamed(name) {
    const start = lines.indexOf(`      - name: ${name}`);
    assert.notEqual(start, -1, `${name} step must exist`);
    const following = stepStarts.filter((index) => index > start);
    const end = following.length ? Math.min(...following) : lines.length;
    return lines.slice(start, end);
  }

  for (const name of expectedNames) {
    const step = stepNamed(name);
    const keys = ["name"];
    for (const line of step.slice(1)) {
      const match = line.match(/^        ([A-Za-z0-9_-]+):.*$/);
      if (match) {
        keys.push(match[1]);
      }
    }
    assert.deepEqual(keys, expectedKeys.get(name), `${name} mapping must stay exact`);
  }

  const checkout = stepNamed("Checkout exact tested revision");
  const checkoutWith = checkout.indexOf("        with:") + 1;
  const checkoutKeys = [];
  for (const line of checkout.slice(checkoutWith)) {
    const match = line.match(/^          ([A-Za-z0-9_-]+):.*$/);
    if (!match) {
      break;
    }
    checkoutKeys.push(match[1]);
  }
  assert.deepEqual(checkoutKeys, ["ref", "persist-credentials"]);

  const verifier = stepNamed("Verify exact tested revision");
  const verifierEnv = verifier.indexOf("        env:") + 1;
  const verifierKeys = [];
  for (const line of verifier.slice(verifierEnv)) {
    const match = line.match(/^          ([A-Za-z0-9_-]+):.*$/);
    if (!match) {
      break;
    }
    verifierKeys.push(match[1]);
  }
  assert.deepEqual(verifierKeys, ["EXPECTED_SHA"]);

  const setupNode = stepNamed("Set up audited Node runtime");
  const setupWith = setupNode.indexOf("        with:") + 1;
  const setupKeys = [];
  for (const line of setupNode.slice(setupWith)) {
    const match = line.match(/^          ([A-Za-z0-9_-]+):.*$/);
    if (!match) {
      break;
    }
    setupKeys.push(match[1]);
  }
  assert.deepEqual(setupKeys, ["node-version", "package-manager-cache"]);
});
