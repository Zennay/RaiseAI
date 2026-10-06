import test from "node:test";
import assert from "node:assert/strict";
import {
  createZCloudExecutor,
  isGenericContinuation
} from "../src/connectors/zcloud.mjs";

function response(status, body, contentType = "application/json; charset=utf-8") {
  return {
    ok: status >= 200 && status < 300,
    status,
    headers: {
      get(name) {
        return String(name).toLowerCase() === "content-type" ? contentType : null;
      }
    },
    async json() {
      return body;
    }
  };
}

function commandAck(commandId, overrides = {}) {
  return {
    ok: true,
    command_id: commandId,
    status: "pending",
    active: true,
    desired_state: "running",
    deduplicated: false,
    forced: false,
    ...overrides
  };
}

function targets({ active = true } = {}) {
  return {
    projects: {
      "ftmo::w1": {
        project_id: "ftmo::w1",
        base_project_id: "ftmo",
        worker_slot: 1,
        worker_count: 2,
        name: "FTMO · worker 1/2",
        desired_state: "running",
        active
      },
      "ftmo::w2": {
        project_id: "ftmo::w2",
        base_project_id: "ftmo",
        worker_slot: 2,
        worker_count: 2,
        name: "FTMO · worker 2/2",
        desired_state: "running",
        active
      },
      "haxlab::w1": {
        project_id: "haxlab::w1",
        base_project_id: "haxlab",
        worker_slot: 1,
        worker_count: 1,
        name: "HaxLab · worker 1/1",
        desired_state: "running",
        active: true
      }
    }
  };
}

test("zCloud connector base URL must be a clean HTTP(S) origin", async () => {
  for (const invalid of [
    "",
    " http://127.0.0.1:8765",
    "http://127.0.0.1:8765 ",
    "ftp://127.0.0.1:8765",
    "http://10.0.0.5:8765",
    "http://zcloud.internal:8765",
    "http://user:pass@127.0.0.1:8765",
    "http://127.0.0.1:\t8765",
    "http://127.0.0.1:87\n65",
    "https://zcloud.in\u0000ternal:8765",
    "http://127.0.0.1:8765/api",
    "http://127.0.0.1:8765?mode=test",
    "http://127.0.0.1:8765#fragment"
  ]) {
    assert.throws(
      () => createZCloudExecutor({ baseUrl: invalid }),
      /zcloud_base_url_invalid/,
      invalid
    );
  }

  assert.doesNotThrow(() =>
    createZCloudExecutor({ baseUrl: "https://zcloud.internal:8765" })
  );
  assert.doesNotThrow(() =>
    createZCloudExecutor({ baseUrl: "http://[::1]:8765" })
  );

  const calls = [];
  const execute = createZCloudExecutor({
    baseUrl: "http://127.0.0.1:8765/",
    fetchImpl: async (url, options = {}) => {
      calls.push({ url, options });
      if (url.endsWith("/api/runner-targets")) {
        return response(200, targets({ active: true }));
      }
      return response(200, commandAck(31));
    }
  });

  const result = await execute({ route: "zcloud_task" }, "Ga door met FTMO");
  assert.equal(result.enabled, true);
  assert.equal(calls[0].url, "http://127.0.0.1:8765/api/runner-targets");
  assert.equal(calls[1].url, "http://127.0.0.1:8765/api/runner-control");
});

test("generic continuation recognizer is strict", () => {
  assert.equal(isGenericContinuation("Ga door met FTMO", ["ftmo"]), true);
  assert.equal(isGenericContinuation("Werk verder met project FTMO", ["ftmo"]), true);
  assert.equal(isGenericContinuation("Werk verder aan FTMO", ["ftmo"]), true);
  assert.equal(isGenericContinuation("Ga door met FTMO en test de pipeline", ["ftmo"]), false);
});

test("current allocated zCloud worker names resolve to the underlying project", async () => {
  const calls = [];
  const execute = createZCloudExecutor({
    fetchImpl: async (url, options = {}) => {
      calls.push({ url, options });
      if (url.endsWith("/api/runner-targets")) {
        return response(200, {
          projects: {
            "ftmo::w1": {
              project_id: "ftmo::w1",
              base_project_id: "ftmo",
              worker_slot: 1,
              worker_count: 2,
              name: "Portfolio Worker 2/7 · FTMO",
              desired_state: "running",
              active: true
            },
            "ftmo::w2": {
              project_id: "ftmo::w2",
              base_project_id: "ftmo",
              worker_slot: 2,
              worker_count: 2,
              name: "Portfolio Worker 5/7 · FTMO",
              desired_state: "running",
              active: true
            }
          }
        });
      }
      return response(200, commandAck(35));
    }
  });

  const result = await execute({ route: "zcloud_task" }, "Ga door met FTMO");

  assert.equal(result.enabled, true);
  assert.equal(result.answer, "FTMO heeft een nieuwe push gekregen in zCloud.");
  assert.equal(calls.length, 2);
});

test("allocated worker names with contradictory project suffixes fail closed", async () => {
  const calls = [];
  const execute = createZCloudExecutor({
    fetchImpl: async (url, options = {}) => {
      calls.push({ url, options });
      return response(200, {
        projects: {
          "ftmo::w1": {
            project_id: "ftmo::w1",
            base_project_id: "ftmo",
            worker_slot: 1,
            worker_count: 2,
            name: "Portfolio Worker 2/7 · FTMO",
            desired_state: "running",
            active: true
          },
          "ftmo::w2": {
            project_id: "ftmo::w2",
            base_project_id: "ftmo",
            worker_slot: 2,
            worker_count: 2,
            name: "Portfolio Worker 5/7 · HaxLab",
            desired_state: "running",
            active: true
          }
        }
      });
    }
  });

  const result = await execute({ route: "zcloud_task" }, "Ga door met FTMO");

  assert.equal(result.enabled, false);
  assert.equal(result.reason, "zcloud_targets_invalid");
  assert.equal(calls.length, 1);
});

test("zCloud display identity cannot alias a different base project", async () => {
  for (const name of [
    "HaxLab · worker 1/1",
    "Portfolio Worker 2/7 · HaxLab"
  ]) {
    const calls = [];
    const execute = createZCloudExecutor({
      fetchImpl: async (url, options = {}) => {
        calls.push({ url, options });
        return response(200, {
          projects: {
            "ftmo::w1": {
              project_id: "ftmo::w1",
              base_project_id: "ftmo",
              worker_slot: 1,
              worker_count: 1,
              name,
              desired_state: "running",
              active: true
            }
          }
        });
      }
    });

    const result = await execute(
      { route: "zcloud_task" },
      "Ga door met HaxLab"
    );

    assert.equal(result.enabled, false, name);
    assert.equal(result.reason, "zcloud_targets_invalid", name);
    assert.equal(calls.length, 1, name);
  }
});

test("canonical zCloud display identities remain valid control aliases", async () => {
  const cases = [
    {
      base: "cloud",
      name: "zCloud · worker 1/1",
      prompt: "Ga door met zCloud"
    },
    {
      base: "zguard",
      name: "zGuard / zBrowse · worker 1/1",
      prompt: "Ga door met zGuard / zBrowse"
    },
    {
      base: "portfolio-review",
      name: "Portfolio Birdseye Review",
      prompt: "Ga door met Portfolio Birdseye Review"
    }
  ];

  let commandId = 90;
  for (const item of cases) {
    const calls = [];
    const execute = createZCloudExecutor({
      fetchImpl: async (url, options = {}) => {
        calls.push({ url, options });
        if (url.endsWith("/api/runner-targets")) {
          const workerKey = item.base + "::w1";
          return response(200, {
            projects: {
              [workerKey]: {
                project_id: workerKey,
                base_project_id: item.base,
                worker_slot: 1,
                worker_count: 1,
                name: item.name,
                desired_state: "running",
                active: true
              }
            }
          });
        }
        return response(200, commandAck(commandId));
      }
    });

    const result = await execute({ route: "zcloud_task" }, item.prompt);

    assert.equal(result.enabled, true, item.name);
    assert.equal(result.commandId, commandId, item.name);
    assert.deepEqual(JSON.parse(calls[1].options.body), {
      project_id: item.base,
      action: "push"
    });
    commandId += 1;
  }
});

test("current portfolio projects accept canonical werk-verder-aan continuation", async () => {
  const calls = [];
  const execute = createZCloudExecutor({
    fetchImpl: async (url, options = {}) => {
      calls.push({ url, options });
      if (url.endsWith("/api/runner-targets")) {
        return response(200, {
          projects: {
            "lightup::w1": {
              project_id: "lightup::w1",
              base_project_id: "lightup",
              worker_slot: 1,
              worker_count: 1,
              name: "LightUp · worker 1/1",
              desired_state: "running",
              active: true
            }
          }
        });
      }
      return response(200, commandAck(73));
    }
  });

  const result = await execute({ route: "zcloud_task" }, "Werk verder aan Light Up");

  assert.equal(result.enabled, true);
  assert.equal(result.provider, "zcloud");
  assert.equal(result.commandId, 73);
  assert.equal(result.answer, "LightUp heeft een nieuwe push gekregen in zCloud.");
  assert.deepEqual(JSON.parse(calls[1].options.body), {
    project_id: "lightup",
    action: "push"
  });
});

test("active project receives push", async () => {
  const calls = [];
  const execute = createZCloudExecutor({
    fetchImpl: async (url, options = {}) => {
      calls.push({ url, options });
      if (url.endsWith("/api/runner-targets")) {
        return response(200, targets({ active: true }));
      }
      return response(200, commandAck(41));
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
      return response(200, commandAck(42));
    }
  });

  const result = await execute({ route: "zcloud_task" }, "Start FTMO");

  assert.equal(result.enabled, true);
  assert.deepEqual(JSON.parse(calls[1].options.body), {
    project_id: "ftmo",
    action: "start"
  });
});


test("malformed target state fails closed before runner control", async () => {
  const calls = [];
  const execute = createZCloudExecutor({
    fetchImpl: async (url, options = {}) => {
      calls.push({ url, options });
      return response(200, {
        projects: {
          "ftmo::w1": {
            project_id: "ftmo::w1",
            base_project_id: "ftmo",
            worker_slot: 1,
            worker_count: 1,
            name: "FTMO · worker 1/1",
            desired_state: "running",
            active: "false"
          }
        }
      });
    }
  });

  const result = await execute({ route: "zcloud_task" }, "Ga door met FTMO");

  assert.equal(result.enabled, false);
  assert.equal(result.reason, "zcloud_targets_invalid");
  assert.equal(calls.length, 1);
});

test("inconsistent worker identities for one zCloud project fail closed", async () => {
  const invalidSnapshots = [
    {
      projects: {
        "ftmo::w1": {
          project_id: "ftmo::w1",
          base_project_id: " ftmo",
          worker_slot: 1,
          worker_count: 2,
          name: "FTMO · worker 1/2",
          desired_state: "running",
          active: true
        }
      }
    },
    {
      projects: {
        "ftmo::w1": {
          project_id: "ftmo::w1",
          base_project_id: "ftmo",
          worker_slot: 1,
          worker_count: 2,
          name: "FTMO · worker 1/2",
          desired_state: "running",
          active: true
        },
        "ftmo::w2": {
          project_id: "ftmo::w2",
          base_project_id: "ftmo",
          worker_slot: 2,
          worker_count: 2,
          name: "HaxLab · worker 2/2",
          desired_state: "running",
          active: false
        }
      }
    },
    {
      projects: {
        "ftmo::w1": {
          project_id: "ftmo::w1",
          base_project_id: "ftmo",
          worker_slot: 1,
          worker_count: 1,
          name: " · worker 1/1",
          desired_state: "running",
          active: true
        }
      }
    }
  ];

  for (const snapshot of invalidSnapshots) {
    const calls = [];
    const execute = createZCloudExecutor({
      fetchImpl: async (url, options = {}) => {
        calls.push({ url, options });
        return response(200, snapshot);
      }
    });

    const result = await execute({ route: "zcloud_task" }, "Ga door met FTMO");

    assert.equal(result.enabled, false);
    assert.equal(result.reason, "zcloud_targets_invalid");
    assert.equal(calls.length, 1);
  }
});

test("zCloud target identities reject non-canonical IDs and unsafe display names", async () => {
  const invalidTargets = [
    {
      key: "FTMO::w1",
      target: {
        project_id: "FTMO::w1",
        base_project_id: "FTMO",
        worker_slot: 1,
        worker_count: 1,
        name: "FTMO · worker 1/1",
        desired_state: "running",
        active: true
      }
    },
    {
      key: "ftmo/ops::w1",
      target: {
        project_id: "ftmo/ops::w1",
        base_project_id: "ftmo/ops",
        worker_slot: 1,
        worker_count: 1,
        name: "FTMO · worker 1/1",
        desired_state: "running",
        active: true
      }
    },
    {
      key: "ftmo::w1",
      target: {
        project_id: "ftmo::w1",
        base_project_id: "ftmo",
        worker_slot: 1,
        worker_count: 1,
        name: " FTMO · worker 1/1",
        desired_state: "running",
        active: true
      }
    },
    {
      key: "ftmo::w1",
      target: {
        project_id: "ftmo::w1",
        base_project_id: "ftmo",
        worker_slot: 1,
        worker_count: 1,
        name: "FTMO\nspoofed",
        desired_state: "running",
        active: true
      }
    }
  ];

  for (const { key, target } of invalidTargets) {
    const execute = createZCloudExecutor({
      fetchImpl: async () => response(200, { projects: { [key]: target } })
    });

    const result = await execute({ route: "zcloud_task" }, "Ga door met FTMO");

    assert.equal(result.enabled, false);
    assert.equal(result.reason, "zcloud_targets_invalid");
  }
});

test("zCloud target key, project_id, base_project_id and worker_slot must agree", async () => {
  const invalidSnapshots = [
    {
      projects: {
        "ftmo::w1": {
          project_id: "haxlab::w1",
          base_project_id: "ftmo",
          worker_slot: 1,
          worker_count: 1,
          name: "FTMO · worker 1/1",
          desired_state: "running",
          active: true
        }
      }
    },
    {
      projects: {
        "ftmo::w2": {
          project_id: "ftmo::w2",
          base_project_id: "ftmo",
          worker_slot: 1,
          worker_count: 1,
          name: "FTMO · worker 1/1",
          desired_state: "running",
          active: true
        }
      }
    },
    {
      projects: {
        "ftmo::w1": {
          project_id: "ftmo::w1",
          base_project_id: "haxlab",
          worker_slot: 1,
          worker_count: 1,
          name: "FTMO · worker 1/1",
          desired_state: "running",
          active: true
        }
      }
    },
    {
      projects: {
        "ftmo::w1": {
          project_id: "ftmo::w1",
          base_project_id: "ftmo",
          worker_slot: "1",
          worker_count: 1,
          name: "FTMO · worker 1/1",
          desired_state: "running",
          active: true
        }
      }
    }
  ];

  for (const snapshot of invalidSnapshots) {
    const calls = [];
    const execute = createZCloudExecutor({
      fetchImpl: async (url, options = {}) => {
        calls.push({ url, options });
        return response(200, snapshot);
      }
    });

    const result = await execute({ route: "zcloud_task" }, "Ga door met FTMO");

    assert.equal(result.enabled, false);
    assert.equal(result.reason, "zcloud_targets_invalid");
    assert.equal(calls.length, 1);
  }
});

test("invalid zCloud desired-state snapshots fail closed", async () => {
  const invalidSnapshots = [
    {
      projects: {
        "ftmo::w1": {
          project_id: "ftmo::w1",
          base_project_id: "ftmo",
          worker_slot: 1,
          worker_count: 1,
          name: "FTMO · worker 1/1",
          active: true
        }
      }
    },
    {
      projects: {
        "ftmo::w1": {
          project_id: "ftmo::w1",
          base_project_id: "ftmo",
          worker_slot: 1,
          worker_count: 1,
          name: "FTMO · worker 1/1",
          desired_state: "sleeping",
          active: false
        }
      }
    },
    {
      projects: {
        "ftmo::w1": {
          project_id: "ftmo::w1",
          base_project_id: "ftmo",
          worker_slot: 1,
          worker_count: 1,
          name: "FTMO · worker 1/1",
          desired_state: "paused",
          active: true
        }
      }
    }
  ];

  for (const snapshot of invalidSnapshots) {
    const calls = [];
    const execute = createZCloudExecutor({
      fetchImpl: async (url, options = {}) => {
        calls.push({ url, options });
        return response(200, snapshot);
      }
    });

    const result = await execute({ route: "zcloud_task" }, "Ga door met FTMO");

    assert.equal(result.enabled, false);
    assert.equal(result.reason, "zcloud_targets_invalid");
    assert.equal(calls.length, 1);
  }
});

test("paused inactive zCloud worker remains a valid start target", async () => {
  const calls = [];
  const execute = createZCloudExecutor({
    fetchImpl: async (url, options = {}) => {
      calls.push({ url, options });
      if (url.endsWith("/api/runner-targets")) {
        return response(200, {
          projects: {
            "ftmo::w1": {
              project_id: "ftmo::w1",
              base_project_id: "ftmo",
              worker_slot: 1,
              worker_count: 1,
              name: "FTMO · worker 1/1",
              desired_state: "paused",
              active: false
            }
          }
        });
      }
      return response(200, commandAck(71));
    }
  });

  const result = await execute({ route: "zcloud_task" }, "Ga door met FTMO");

  assert.equal(result.enabled, true);
  assert.deepEqual(JSON.parse(calls[1].options.body), {
    project_id: "ftmo",
    action: "start"
  });
});


test("zCloud target snapshots bound project cardinality", async () => {
  const projects = {};
  for (let index = 1; index <= 257; index += 1) {
    const project = "p" + index;
    projects[project + "::w1"] = {
      project_id: project + "::w1",
      base_project_id: project,
      worker_slot: 1,
      worker_count: 1,
      name: "Project " + index + " · worker 1/1",
      desired_state: "running",
      active: true
    };
  }

  const calls = [];
  const execute = createZCloudExecutor({
    fetchImpl: async (url, options = {}) => {
      calls.push({ url, options });
      return response(200, { projects });
    }
  });

  const result = await execute({ route: "zcloud_task" }, "Ga door met p1");

  assert.equal(result.enabled, false);
  assert.equal(result.reason, "zcloud_targets_invalid");
  assert.equal(calls.length, 1);
});

test("zCloud target display names have a bounded canonical length", async () => {
  for (const length of [257, 4_096]) {
    const calls = [];
    const execute = createZCloudExecutor({
      fetchImpl: async (url, options = {}) => {
        calls.push({ url, options });
        if (url.endsWith("/api/runner-targets")) {
          return response(200, {
            projects: {
              "ftmo::w1": {
                project_id: "ftmo::w1",
                base_project_id: "ftmo",
                worker_slot: 1,
                worker_count: 1,
                name: "F".repeat(length),
                desired_state: "running",
                active: true
              }
            }
          });
        }
        return response(200, commandAck(81));
      }
    });

    const result = await execute({ route: "zcloud_task" }, "Ga door met FTMO");

    assert.equal(result.enabled, false);
    assert.equal(result.reason, "zcloud_targets_invalid");
    assert.equal(calls.length, 1);
  }

  const calls = [];
  const execute = createZCloudExecutor({
    fetchImpl: async (url, options = {}) => {
      calls.push({ url, options });
      if (url.endsWith("/api/runner-targets")) {
        return response(200, {
          projects: {
            "ftmo::w1": {
              project_id: "ftmo::w1",
              base_project_id: "ftmo",
              worker_slot: 1,
              worker_count: 1,
              name: "F".repeat(256),
              desired_state: "running",
              active: true
            }
          }
        });
      }
      return response(200, commandAck(82));
    }
  });

  const result = await execute({ route: "zcloud_task" }, "Ga door met FTMO");

  assert.equal(result.enabled, true);
  assert.equal(result.commandId, 82);
  assert.equal(calls.length, 2);
});

test("incomplete or inconsistent worker-count snapshots fail closed", async () => {
  const invalidSnapshots = [
    {
      projects: {
        "ftmo::w1": {
          project_id: "ftmo::w1",
          base_project_id: "ftmo",
          worker_slot: 1,
          worker_count: 2,
          name: "FTMO · worker 1/2",
          desired_state: "running",
          active: true
        }
      }
    },
    {
      projects: {
        "ftmo::w1": {
          project_id: "ftmo::w1",
          base_project_id: "ftmo",
          worker_slot: 1,
          worker_count: 2,
          name: "FTMO · worker 1/2",
          desired_state: "running",
          active: true
        },
        "ftmo::w2": {
          project_id: "ftmo::w2",
          base_project_id: "ftmo",
          worker_slot: 2,
          worker_count: 3,
          name: "FTMO · worker 2/3",
          desired_state: "running",
          active: false
        }
      }
    },
    {
      projects: {
        "ftmo::w2": {
          project_id: "ftmo::w2",
          base_project_id: "ftmo",
          worker_slot: 2,
          worker_count: 1,
          name: "FTMO · worker 2/1",
          desired_state: "running",
          active: true
        }
      }
    }
  ];

  for (const snapshot of invalidSnapshots) {
    const calls = [];
    const execute = createZCloudExecutor({
      fetchImpl: async (url, options = {}) => {
        calls.push({ url, options });
        return response(200, snapshot);
      }
    });

    const result = await execute({ route: "zcloud_task" }, "Ga door met FTMO");

    assert.equal(result.enabled, false);
    assert.equal(result.reason, "zcloud_targets_invalid");
    assert.equal(calls.length, 1);
  }
});

test("sparse large worker counts fail closed without range enumeration", async () => {
  const calls = [];
  const execute = createZCloudExecutor({
    fetchImpl: async (url, options = {}) => {
      calls.push({ url, options });
      return response(200, {
        projects: {
          "ftmo::w1": {
            project_id: "ftmo::w1",
            base_project_id: "ftmo",
            worker_slot: 1,
            worker_count: 1_000_000,
            name: "FTMO · worker 1/1000000",
            desired_state: "running",
            active: true
          }
        }
      });
    }
  });

  const result = await execute({ route: "zcloud_task" }, "Ga door met FTMO");

  assert.equal(result.enabled, false);
  assert.equal(result.reason, "zcloud_targets_invalid");
  assert.equal(calls.length, 1);
});

test("ambiguous project aliases never dispatch a command", async () => {
  const calls = [];
  const execute = createZCloudExecutor({
    fetchImpl: async (url, options = {}) => {
      calls.push({ url, options });
      return response(200, {
        projects: {
          "alpha::w1": {
            project_id: "alpha::w1",
            base_project_id: "alpha",
            worker_slot: 1,
            worker_count: 1,
            name: "Shared · worker 1/1",
            desired_state: "running",
            active: true
          },
          "beta::w1": {
            project_id: "beta::w1",
            base_project_id: "beta",
            worker_slot: 1,
            worker_count: 1,
            name: "Shared · worker 1/1",
            desired_state: "running",
            active: false
          }
        }
      });
    }
  });

  const result = await execute({ route: "zcloud_task" }, "Ga door met Shared");

  assert.equal(result.enabled, false);
  assert.equal(result.reason, "zcloud_project_ambiguous");
  assert.match(result.answer, /niets gestart/);
  assert.equal(calls.length, 1);
});

test("successful zCloud target snapshots require JSON response media type", async () => {
  const execute = createZCloudExecutor({
    fetchImpl: async url => {
      assert.match(url, /\/api\/runner-targets$/);
      return response(200, targets({ active: true }), "text/plain");
    }
  });

  const result = await execute({ route: "zcloud_task" }, "Ga door met FTMO");

  assert.equal(result.enabled, false);
  assert.equal(result.reason, "zcloud_targets_invalid");
});

test("zCloud JSON response media type only accepts bare JSON or UTF-8 charset", async () => {
  for (const contentType of [
    "application/json",
    "application/json; charset=utf-8",
    "Application/JSON; Charset=UTF-8",
    'application/json; charset="UTF-8"'
  ]) {
    const execute = createZCloudExecutor({
      fetchImpl: async url => {
        if (url.endsWith("/api/runner-targets")) {
          return response(200, targets({ active: true }), contentType);
        }
        return response(200, commandAck(83), contentType);
      }
    });

    const result = await execute({ route: "zcloud_task" }, "Ga door met FTMO");
    assert.equal(result.enabled, true, contentType);
    assert.equal(result.commandId, 83, contentType);
  }

  for (const contentType of [
    "application/json;",
    "application/json; charset=iso-8859-1",
    "application/json; charset=utf-8; profile=test",
    "application/json; profile=test",
    "application/json; charset=utf-8; charset=utf-8"
  ]) {
    const targetExecute = createZCloudExecutor({
      fetchImpl: async () => response(200, targets({ active: true }), contentType)
    });

    const targetResult = await targetExecute(
      { route: "zcloud_task" },
      "Ga door met FTMO"
    );
    assert.equal(targetResult.enabled, false, contentType);
    assert.equal(targetResult.reason, "zcloud_targets_invalid", contentType);

    const ackExecute = createZCloudExecutor({
      fetchImpl: async url => {
        if (url.endsWith("/api/runner-targets")) {
          return response(200, targets({ active: true }));
        }
        return response(200, commandAck(84), contentType);
      }
    });

    const ackResult = await ackExecute(
      { route: "zcloud_task" },
      "Ga door met FTMO"
    );
    assert.equal(ackResult.enabled, false, contentType);
    assert.equal(ackResult.reason, "zcloud_invalid_ack", contentType);
  }
});

test("successful zCloud command acknowledgements require JSON response media type", async () => {
  const execute = createZCloudExecutor({
    fetchImpl: async url => {
      if (url.endsWith("/api/runner-targets")) {
        return response(200, targets({ active: true }));
      }
      return response(200, commandAck(81), "text/html");
    }
  });

  const result = await execute({ route: "zcloud_task" }, "Ga door met FTMO");

  assert.equal(result.enabled, false);
  assert.equal(result.reason, "zcloud_invalid_ack");
  assert.match(result.answer, /niet als gestart/);
});

test("successful HTTP status requires canonical zCloud command acknowledgement", async () => {
  const invalidAcks = [
    null,
    {},
    { ok: false, command_id: 51, status: "pending" },
    { ok: true, command_id: null, status: "pending" },
    { ok: true, command_id: 0, status: "pending" },
    { ok: true, command_id: 1.5, status: "pending" },
    { ok: true, command_id: 52, status: "completed" },
    commandAck(53, { active: false }),
    commandAck(54, { desired_state: "paused" }),
    commandAck(55, { deduplicated: "false" }),
    commandAck(56, { forced: true })
  ];

  for (const acknowledgement of invalidAcks) {
    const execute = createZCloudExecutor({
      fetchImpl: async url => {
        if (url.endsWith("/api/runner-targets")) {
          return response(200, targets({ active: true }));
        }
        return response(200, acknowledgement);
      }
    });

    const result = await execute({ route: "zcloud_task" }, "Ga door met FTMO");

    assert.equal(result.enabled, false);
    assert.equal(result.reason, "zcloud_invalid_ack");
    assert.match(result.answer, /niet als gestart/);
  }
});

test("valid zCloud acknowledgement may be deduplicated but must remain coherent", async () => {
  const execute = createZCloudExecutor({
    fetchImpl: async url => {
      if (url.endsWith("/api/runner-targets")) {
        return response(200, targets({ active: true }));
      }
      return response(200, commandAck(61, { deduplicated: true }));
    }
  });

  const result = await execute({ route: "zcloud_task" }, "Ga door met FTMO");

  assert.equal(result.enabled, true);
  assert.equal(result.commandId, 61);
  assert.equal(result.reason, "zcloud_command_queued");
});

test("zCloud rejection details stay secret-safe", async () => {
  for (const error of ["   ", "token=super-secret", "/srv/zcloud/private.sqlite"]) {
    const execute = createZCloudExecutor({
      fetchImpl: async url => {
        if (url.endsWith("/api/runner-targets")) {
          return response(200, targets({ active: true }));
        }
        return response(409, { error });
      }
    });

    const result = await execute({ route: "zcloud_task" }, "Ga door met FTMO");

    assert.equal(result.enabled, false);
    assert.equal(result.reason, "zcloud_command_rejected");
    assert.equal(result.answer, "zCloud heeft de opdracht niet geaccepteerd.");
    if (error.trim()) assert.equal(result.answer.includes(error.trim()), false);
  }
});


test("zCloud target display names reject invisible Unicode controls", async () => {
  for (const name of ["FTMO\u202Espoofed", "FTMO\u200Binvisible"]) {
    const execute = createZCloudExecutor({
      fetchImpl: async () =>
        response(200, {
          projects: {
            "ftmo::w1": {
              project_id: "ftmo::w1",
              base_project_id: "ftmo",
              worker_slot: 1,
              worker_count: 1,
              name,
              desired_state: "running",
              active: true
            }
          }
        })
    });

    const result = await execute({ route: "zcloud_task" }, "Ga door met FTMO");
    assert.equal(result.enabled, false, JSON.stringify(name));
    assert.equal(result.reason, "zcloud_targets_invalid", JSON.stringify(name));
  }
});
