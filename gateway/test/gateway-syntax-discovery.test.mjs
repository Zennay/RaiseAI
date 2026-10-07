import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(HERE, "../..");
const WORKFLOW = fs.readFileSync(
  path.join(ROOT, ".github", "workflows", "gateway-test.yml"),
  "utf8",
);

function collectMjs(root) {
  const files = [];
  for (const entry of fs.readdirSync(root, { withFileTypes: true })) {
    const absolute = path.join(root, entry.name);
    if (entry.isDirectory()) {
      files.push(...collectMjs(absolute));
    } else if (entry.isFile() && entry.name.endsWith(".mjs")) {
      files.push(path.relative(path.join(ROOT, "gateway"), absolute).replaceAll(path.sep, "/"));
    }
  }
  return files.sort();
}

test("gateway syntax step discovers runtime and deploy modules dynamically", () => {
  const required = [
    "          mapfile -d '' node_files < <(find deploy src -type f -name '*.mjs' -print0 | sort -z)",
    '          test "${#node_files[@]}" -gt 0',
    '          for path in "${node_files[@]}"; do',
    '            node --check "$path"',
  ];
  for (const line of required) {
    assert.equal(
      WORKFLOW.split(line).length - 1,
      1,
      `expected one dynamic syntax-discovery command: ${line}`,
    );
  }

  assert.equal(
    WORKFLOW.split("node --check").length - 1,
    1,
    "syntax validation must not drift back to a hand-maintained Node file allowlist",
  );
  assert.doesNotMatch(
    WORKFLOW,
    /node --check\s+(?:deploy|src)\//,
    "individual gateway modules must not be manually enumerated",
  );
});

test("current dynamic syntax surface includes nested runtime and deploy modules", () => {
  const gatewayRoot = path.join(ROOT, "gateway");
  const files = [
    ...collectMjs(path.join(gatewayRoot, "deploy")),
    ...collectMjs(path.join(gatewayRoot, "src")),
  ].sort();

  assert.ok(files.length >= 20, "expected the current gateway runtime/deploy MJS surface");
  for (const expected of [
    "deploy/read-key-value-file.mjs",
    "deploy/readiness-http.mjs",
    "deploy/smoke-http.mjs",
    "src/app.mjs",
    "src/connectors/zcloud.mjs",
    "src/providers/openai.mjs",
    "src/providers/openrouter.mjs",
    "src/router.mjs",
  ]) {
    assert.ok(files.includes(expected), `dynamic surface must include ${expected}`);
  }
});
