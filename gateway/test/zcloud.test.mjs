import test from "node:test";
import assert from "node:assert/strict";
import {
  createZCloudExecutor,
  isGenericContinuation
} from "../src/connectors/zcloud.mjs";

function response(status, body) {
  return {
    ok: status >= 200 && status < 300,
    status,
    async json() {
      return body;
    }
  };
}

function targets({ active = true } = {}) {
  return {
    projects: {
      "ftmo::w1": {
        base_project_id: "ftmo",
        name: "FTMO · worker 1/2",
        active
      },
      "ftmo::w2": {
        base_project_id: "ftmo",
        name: "FTMO · worker 2/2",
        active
      },
      "haxlab::w1": {
        base_project_id: "haxlab",
        name: "HaxLab · worker 1/1",
        active: true
      }
    }
  };
}

test("generic continuation recognizer is strict", () => {
  assert.equal(isGenericContinuation("Ga door met FTMO", ["ftmo"]), true);
  assert.equal(isGenericContinuation("Werk verder met project FTMO", ["ftmo"]), true);
  assert.equal(isGenericContinuation("Ga door met FTMO en test de pipeline", ["ftmo"]), false);
});

test("active project receives push", async () => {
  const calls = [];
  const execute = createZCloudExecutor({
    fetchImpl: async (url, options = {}) => {
      calls.push({ url, options });
      if (url.endsWith("/api/runner-targets")) {
        return response(200, targets({ active: true }));
      }
      return response(200, { ok: true, command_id: 41, status: "pending" });
    }
  });

  const result = await execute({ route: "zcloud_task" }, "Ga door met FTMO");

  assert.equal(result.enabled, true);
  assert.equal(result.provider, "zcloud");
  assert.equal(result.commandId, 41);
  assert.equal(calls.length, 2);
  assert.deepEqual(JSON.parse(calls[1].options.body), {
    project_id: "ftmo",
    action: "push"
  });
});

test("inactive project receives start", async () => {
  const calls = [];
  const execute = createZCloudExecutor({
    fetchImpl: async (url, options = {}) => {
      calls.push({ url, options });
      if (url.endsWith("/api/runner-targets")) {
        return response(200, targets({ active: false }));
      }
      return response(200, { ok: true, command_id: 42, status: "pending" });
    }
  });

  const result = await execute({ route: "zcloud_task" }, "Start FTMO");

  assert.equal(result.enabled, true);
  assert.deepEqual(JSON.parse(calls[1].options.body), {
    project_id: "ftmo",
    action: "start"
  });
});
