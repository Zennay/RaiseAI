import assert from "node:assert/strict";
import { execFileSync, spawnSync } from "node:child_process";
import { lstatSync, readFileSync } from "node:fs";
import { dirname, extname, resolve } from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const WORKFLOW_PATH = resolve(
  ROOT,
  ".github",
  "workflows",
  "javascript-surface-contract.yml",
);
function decodeUtf8Strict(bytes, label) {
  try {
    return new TextDecoder("utf-8", { fatal: true }).decode(bytes);
  } catch (error) {
    throw new Error(`${label} must be strict UTF-8`, { cause: error });
  }
}

const WORKFLOW = decodeUtf8Strict(
  readFileSync(WORKFLOW_PATH),
  ".github/workflows/javascript-surface-contract.yml",
);
const EXTENSIONS = new Set([".js", ".mjs", ".cjs"]);
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

test("every tracked JavaScript file is regular and syntax-valid", () => {
  for (const relative of trackedJavaScriptPaths()) {
    const absolute = resolve(ROOT, relative);
    const stat = lstatSync(absolute);
    assert.equal(
      stat.isSymbolicLink(),
      false,
      `${relative} must not use symlink indirection`,
    );
    assert.equal(stat.isFile(), true, `${relative} must be a regular file`);
    decodeUtf8Strict(readFileSync(absolute), relative);

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

test("strict UTF-8 decoding rejects malformed source bytes", () => {
  assert.throws(
    () => decodeUtf8Strict(Buffer.from([0x66, 0x6f, 0x80, 0x6f]), "fixture.js"),
    /fixture[.]js must be strict UTF-8/,
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
